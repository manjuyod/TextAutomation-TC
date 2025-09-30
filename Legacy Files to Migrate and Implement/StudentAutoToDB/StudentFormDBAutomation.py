import email
from bs4 import BeautifulSoup
import requests
import os
import re
from datetime import datetime
import base64
import json
import pprint
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import googleapiclient
from googleapiclient.discovery import build

############################################
# Gmail API helper (replaces imaplib usage)#
############################################

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service() -> "googleapiclient.discovery.Resource":
    """Authorise (or refresh) and return a Gmail API service resource."""
    TOKEN_PATH = 'C:\\Users\\Administrator\\Desktop\\Scripts\\reporting-v1\\ReportScripts\\StudentAutoToDB\\token.json'
    creds = None
    try:
        if os.path.exists(TOKEN_PATH):                     # cached access/refresh
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                secret_json = json.loads(os.environ['StudentAutoAPI'])
                flow = InstalledAppFlow.from_client_config(secret_json, SCOPES)
                creds = flow.run_local_server(
                    port=0,
                    access_type='offline',
                    prompt='consent'
                )
            with open(TOKEN_PATH, 'w') as token:
                token.write(creds.to_json())
    except Exception as e:
        # Notify on Telegram that auth failed and needs manual re‑run
        err_msg = f"🚨 Gmail API auth error: {e} - Please re‑run interactively to regenerate token.json."
        send_telegram_message(err_msg, log_bot, log_chat)
        # re‑raise so your script sees the failure
        raise
         
    return build('gmail', 'v1', credentials=creds)

class DummyMail:
    """Provides .close() / .logout() so downstream code is unchanged."""
    def close(self):  pass
    def logout(self): pass

##################################
# Telegram Bot                   #
##################################

auto_bot = os.getenv("TCAutoBotToken")
auto_chat = os.getenv("TCAutoChatID")
log_bot = os.getenv("TCLogBotToken")
log_chat = os.getenv("TCLogBotChatID")

def send_telegram_message(message, bot_token, chat_id):
    """
    Sends a message to Telegram using the Bot API.
    Requires the environment variables TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
    """

    if not bot_token or not chat_id:
        print("Telegram credentials not set; skipping Telegram notification.")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print("Error sending Telegram message:", response.text)
    except Exception as e:
        print("Error sending Telegram message:", e)

###########################
# Email Retrieval Methods #
###########################

def get_unread_emails():
    """
    Returns [(msg_id, email.message.Message), …]  and a dummy 'mail' object.
    Signature matches the original imaplib version so main() is untouched.
    """
    service = get_gmail_service()
    resp = service.users().messages().list(userId='me', q='is:unread').execute()
    msgs = []
    for m in resp.get('messages', []):
        raw = service.users().messages().get(userId='me', id=m['id'], format='raw').execute()['raw']
        msg_bytes = base64.urlsafe_b64decode(raw.encode('ascii'))
        msg = email.message_from_bytes(msg_bytes)
        msgs.append((m['id'], msg))
    return msgs, DummyMail()

def extract_email_body(msg):
    """
    Extract the body from an email.
    If the message contains a <ul>, preserve its HTML so that bullet boundaries remain.
    """
    body = None
    if msg.is_multipart():
        html_content = None
        for part in msg.walk():
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
            except Exception as e:
                print(f"Error decoding part: {e}")
                continue
            if ctype == 'text/plain' and payload:
                try:
                    body = payload.decode('utf-8', errors='ignore')
                    break
                except Exception as e:
                    print(f"Error decoding text/plain: {e}")
            elif ctype == 'text/html' and payload and body is None:
                try:
                    html_content = payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding text/html: {e}")
        if not body and html_content:
            # Do not strip HTML if it contains bullet lists.
            body = html_content
    else:
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
        except Exception as e:
            print(f"Error decoding email: {e}")
            return None
        if ctype == 'text/plain' and payload:
            body = payload.decode('utf-8', errors='ignore')
        elif ctype == 'text/html' and payload:
            body = payload.decode('utf-8', errors='ignore')
    return body

def mark_as_read(service, msg_id):
    """Remove the UNREAD label (requires gmail.modify scope)."""
    service.users().messages().modify(
        userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
    ).execute()

#####################################
# Helper Functions for Parsing      #
#####################################

def calculate_age(dob_str, current_date=None):
    """Calculates age in years from a DOB string in MM/DD/YYYY format."""
    if current_date is None:
        current_date = datetime.now()
    try:
        dob = datetime.strptime(dob_str, "%m/%d/%Y")
        age = current_date.year - dob.year - ((current_date.month, current_date.day) < (dob.month, dob.day))
        return age
    except Exception as e:
        print(f"Error calculating age for {dob_str}: {e}")
        return None

def extract_web_link(html):
    """
    Searches the entire HTML text for a URL starting with 'https://tutoringclub.com/'
    that contains 'student-intake-form'.
    """
    match = re.search(r'(https://tutoringclub\.com/[^\s"<]+student-intake-form/?\b)', html)
    if match:
        return match.group(1)
    return None

##################################
# Franchise Lookup Function      #
##################################

franchise_info = [
    (1, 'Test', 'https://tutoringclub.com/student-intake-form/', None),
    (57, 'Gilbert', 'https://tutoringclub.com/gilbertaz/student-intake-form/', 'https://tutoringclub.com/gilbertaz/assessment-payment-form/'),
    (6, 'Anthem', 'https://tutoringclub.com/anthemnv/student-intake-form/', 'https://tutoringclub.com/anthemnv/assessment-payment-form/'),
    (11, 'Green Valley', 'https://tutoringclub.com/hendersonnv/student-intake-form/', 'https://tutoringclub.com/hendersonnv/assessment-payment-form/'),
    (15, 'North LV', 'https://tutoringclub.com/northlasvegasnv/student-intake-form/', 'https://tutoringclub.com/northlasvegasnv/assessment-payment-form/'),
    (16, 'Rhodes Ranch', 'https://tutoringclub.com/rhodesranchnv/student-intake-form/', 'https://tutoringclub.com/rhodesranchnv/assessment-payment-form/'),
    (60, 'Centennial', 'https://tutoringclub.com/centennialnv/student-intake-form/', 'https://tutoringclub.com/centennialnv/assessment-payment-form/'),
    (24, 'North Fresno', 'https://tutoringclub.com/fresnoca/student-intake-form/', 'https://tutoringclub.com/fresnoca/assessment-payment-form/'),
    (8, 'Fountain Valley CA', 'https://tutoringclub.com/fountain-valley-ca/student-intake-form/', None),
    (20, 'Clovis', 'https://tutoringclub.com/clovisca/student-intake-form/', None),
    (87, 'Downey', 'https://tutoringclub.com/downeyca/student-intake-form/', None)
]

def get_franchise_links(web_link):
    """
    Given a web_link, normalize trailing slashes and return a dict with the matching franchise_id.
    """
    if web_link is None:
        return {'franchise_id': None}
    normalized_link = web_link.rstrip('/')
    for franchise in franchise_info:
        franchise_link = franchise[2]
        if franchise_link is not None and franchise_link.rstrip('/') == normalized_link:
            return {'franchise_id': franchise[0]}
    return {'franchise_id': None}

##################################
# Parsing HTML to Mapping        #
##################################

def parse_html_to_mapping(html):
    """
    Parses the HTML form content and returns a mapping that mirrors the master_sub_template.
    This function groups rows by section headers (e.g. "Address", "Student 1", etc.)
    and preserves HTML for answers that include bullet lists.
    """
    soup = BeautifulSoup(html, "html.parser")
    inner_table = soup.find("table", {"bgcolor": "#FFFFFF"})
    if not inner_table:
        print("Inner table not found.")
        return {}
    rows = inner_table.find_all("tr")
    
    data = []
    for row in rows:
        # Preserve bullet list HTML if present.
        ul = row.find("ul")
        if ul:
            answer = str(ul)
        else:
            answer = row.get_text(" ", strip=True)
        td = row.find("td", colspan=True)
        if td and "font-size:14px" in td.get("style", "") and td.get_text(strip=True):
            header_text = td.get_text(strip=True)
            data.append(("header", header_text))
        else:
            strong = row.find("strong")
            if strong:
                question = strong.get_text(" ", strip=True)
                data.append(("question", question))
            else:
                if answer:
                    data.append(("answer", answer))
    
    # Group rows by header.
    sections = {}
    current_section = None
    i = 0
    while i < len(data):
        typ, content = data[i]
        if typ == "header":
            current_section = content
            sections[current_section] = []
            i += 1
        elif typ == "question":
            if i + 1 < len(data) and data[i+1][0] == "answer":
                q = content
                a = data[i+1][1]
                if current_section is None:
                    current_section = "General"
                    sections[current_section] = []
                sections[current_section].append((q, a))
                i += 2
            else:
                i += 1
        else:
            i += 1

    result = {
        "franchise_id": None,
        "student_info": [{
            "home_address": None,
            "siblings": None,
            "student_1": {},
            "student_2": {},
            "student_3": {},
            "student_4": {}
        }],
        "parent_info": [{}]
    }
    
    # Address mapping.
    if "Address" in sections:
        addr = {}
        for q, a in sections["Address"]:
            if "Street Address" in q:
                addr["addr_line1"] = a
            elif "City" in q:
                addr["city"] = a
            elif "State" in q:
                addr["state"] = a
            elif "ZIP" in q or "Postal Code" in q:
                addr["postal"] = a
        addr.setdefault("addr_line1", "")
        addr.setdefault("addr_line2", "")
        addr.setdefault("city", "")
        addr.setdefault("state", "")
        addr.setdefault("postal", "")
        result["student_info"][0]["home_address"] = addr

    # Siblings mapping.
    student_checkbox_key = None
    for key in sections:
        if "student-checkboxes" in key.lower():
            student_checkbox_key = key
            break
    siblings_list = []
    if student_checkbox_key:
        answer_text = sections[student_checkbox_key][0][1]
        siblings_list = re.findall(r"Student-\d+", answer_text)
    result["student_info"][0]["siblings"] = {
        "has_siblings": bool(siblings_list),
        "number_of_siblings": len(siblings_list)
    }
    
    # Student basic info mapping.
    students = ["Student 1", "Student 2", "Student 3", "Student 4"]
    for idx, student_key in enumerate(students, start=1):
        if student_key in sections:
            student_data = sections[student_key]
            student_entry = {}
            first_name = None
            last_name = None
            dob = None
            grade = None
            for q, a in student_data:
                if "First Name" in q:
                    first_name = a
                elif "Last Name" in q:
                    last_name = a
                elif "Date of Birth" in q:
                    dob = a  # Expecting MM/DD/YYYY
                elif "Grade" in q:
                    grade = a
            age = calculate_age(dob) if dob else None
            student_entry["name"] = {"FirstName": first_name, "LastName": last_name}
            student_entry["dob"] = dob
            student_entry["grade"] = grade
            student_entry["age"] = age
            result["student_info"][0][f"student_{idx}"] = student_entry

    # Academic Goals mapping.
    if "Parental Objectives" in sections:
        aqas = sections["Parental Objectives"]
        block_size = 6
        academic_blocks = [aqas[i:i+block_size] for i in range(0, len(aqas), block_size)]
        mapping_keys = ["desired_status", "attitude_school", "improvement", "concerns", "motivation", "additional_notes"]
        for i, block in enumerate(academic_blocks):
            if i < 4:
                goals = {}
                for (q, a), key in zip(block, mapping_keys):
                    a = a.strip() if a else None
                    if key in ["improvement", "concerns"] and a:
                        if "<ul" in a.lower():
                            bullet_soup = BeautifulSoup(a, "html.parser")
                            first_li = bullet_soup.find("li")
                            if first_li:
                                a = first_li.get_text(strip=True)
                        else:
                            bullets = [line.strip() for line in a.splitlines() if line.strip()]
                            if len(bullets) < 2:
                                bullets = re.split(r'\s{2,}', a)
                                bullets = [b.strip() for b in bullets if b.strip()]
                            a = bullets[0] if bullets else a
                    if key == "motivation" and (a is None or a not in ["High", "Average", "Below Average", "Very Low"]):
                        a = None
                    goals[key] = a
                result["student_info"][0][f"student_{i+1}"]["academic_goals"] = goals

    # Medical Information mapping.
    med_phrases = {
        "vision_problems": "Any other eye or vision problems?",
        "hearing_problems": "Any hearing problems?",
        "speech_impairments": "Any speech inpairments?",
        "early_childhood_health_issues": "Any early childhood health issues?",
        "current_health_issues": "Any current health issues?",
        "current_medications": "Any current medications?",
        "psychological_evaluation": "Has your student ever had a psychological or neurological evaluation?"
    }
    
    def find_med_category(block, phrase, is_psych_eval=False):
        for idx, (q, a) in enumerate(block):
            if is_psych_eval:
                if "psychological" in q.lower() and "evaluation" in q.lower():
                    yes_answer = a.strip()
                    explanation = block[idx+1][1].strip() if idx+1 < len(block) else None
                    return yes_answer, explanation
            else:
                if phrase.lower() in q.lower():
                    yes_answer = a.strip()
                    explanation = block[idx+1][1].strip() if idx+1 < len(block) else None
                    return yes_answer, explanation
        return None, None

    if "Medical Information" in sections:
        med_pairs = sections["Medical Information"]
        start_indices = [i for i, (q, a) in enumerate(med_pairs)
                         if "any other eye or vision problems?" in q.lower()]
        med_blocks = []
        for i, start in enumerate(start_indices):
            if i < len(start_indices) - 1:
                block = med_pairs[start : start_indices[i+1]]
            else:
                block = med_pairs[start:]
            med_blocks.append(block)
        for i, block in enumerate(med_blocks):
            med_info = {}
            for key, phrase in med_phrases.items():
                if key == "psychological_evaluation":
                    yes_answer, explanation = find_med_category(block, phrase, is_psych_eval=True)
                    med_info[key] = {"has_evaluation": yes_answer, "details": explanation}
                else:
                    yes_answer, explanation = find_med_category(block, phrase)
                    med_info[key] = {"issue": yes_answer, "details": explanation}
            for key in med_phrases.keys():
                if key == "psychological_evaluation":
                    if med_info.get(key, {}).get("has_evaluation") is None:
                        med_info[key] = {"has_evaluation": None, "details": None}
                else:
                    if med_info.get(key, {}).get("issue") is None:
                        med_info[key] = {"issue": None, "details": None}
            med_info["glasses"] = "No"
            if i < 4:
                result["student_info"][0][f"student_{i+1}"]["medical_info"] = med_info

    # Parent Information mapping.
    parent_info = {}
    if "Parent or Guardian 1" in sections:
        data_pg1 = sections["Parent or Guardian 1"]
        first_name = last_name = occupation = employer = email_addr = cell = None
        for q, a in data_pg1:
            if "First Name" in q:
                first_name = a
            elif "Last Name" in q:
                last_name = a
            elif "Occupation" in q:
                occupation = a
            elif "Employer" in q:
                employer = a
            elif "Email" in q:
                email_addr = a
            elif "Phone" in q:
                cell = a
        parent_info["parent_1"] = {
            "full_name": {"first": first_name, "last": last_name},
            "occupation": occupation,
            "employer": employer,
            "cell": cell,
            "email": email_addr,
            "permission_to_text": None
        }
    if "Parent or Guardian 2" in sections:
        data_pg2 = sections["Parent or Guardian 2"]
        first_name = last_name = occupation = employer = email_addr = cell = None
        for q, a in data_pg2:
            if "First Name" in q:
                first_name = a
            elif "Last Name" in q:
                last_name = a
            elif "Occupation" in q:
                occupation = a
            elif "Employer" in q:
                employer = a
            elif "Email" in q:
                email_addr = a
            elif "Phone" in q:
                cell = a
        parent_info["parent_2"] = {
            "full_name": {"first": first_name, "last": last_name},
            "occupation": occupation,
            "employer": employer,
            "cell": cell,
            "email": email_addr,
            "permission_to_text": None
        }
    if "Emergency Contact" in sections:
        data_ec = sections["Emergency Contact"]
        first_name = last_name = phone_number = None
        for q, a in data_ec:
            if "First Name" in q:
                first_name = a
            elif "Last name" in q:
                last_name = a
            elif "Phone" in q:
                phone_number = a
        parent_info["emergency_contact"] = {
            "name": {"first": first_name, "last": last_name},
            "phone_number": phone_number,
            "type": "Relative"
        }
    result["parent_info"] = [parent_info]
    
    return result

##################################
# Count Non-Empty Students        #
##################################

def count_students(template):
    """Counts non-empty student entries in template['student_info'][0]."""
    try:
        student_info = template.get('student_info', [{}])[0]
        count = 0
        for key in student_info:
            if key.startswith("student_") and student_info[key]:
                count += 1
        return count
    except Exception as e:
        print(f"Error counting students: {e}")
        return 0

##################################
# Sanitization Function          #
##################################

def sanitize_for_sql(input_string, max_length=None, is_numeric=False):
    """Sanitize input for SQL by trimming whitespace and escaping apostrophes."""
    if input_string is None:
        return "NULL"
    sanitized_string = input_string.strip()
    sanitized_string = sanitized_string.replace("'", "''")
    if is_numeric:
        if not sanitized_string.isdigit():
            return "Invalid input: Expected numeric value"
    if max_length is not None and len(sanitized_string) > max_length:
        return f"Invalid input: Exceeds maximum length of {max_length}"
    return sanitized_string

def format_phone_number(phone_str):
    """
    Formats a phone number string into the format: (111) 111-1111.
    It removes all non-digit characters, strips a leading '1' if present,
    and then returns the formatted phone number if there are exactly 10 digits.
    Otherwise, it returns the original string.
    """
    if not phone_str:
        return None
    digits = re.sub(r'\D', '', phone_str)
    # Remove a leading '1' if present
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return phone_str  # or return None if you prefer
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

##################################
# Generate SQL Query Function    #
##################################

def generate_sql_query(input_data, template, student_count):
    """Generate the SQL query string for executing a stored procedure."""
    def sanitize_value(value):
        if value is None or value == "":
            return "NULL"
        elif isinstance(value, str):
            return f"'{sanitize_for_sql(value)}'"
        else:
            return f"'{str(value)}'"
    
    address_info = template['student_info'][0].get('home_address', {})
    parent_1 = template['parent_info'][0].get('parent_1', {})
    parent_2 = template['parent_info'][0].get('parent_2', {})
    emergency_contact = template['parent_info'][0].get('emergency_contact', {})

    father_full_name = parent_1.get('full_name', {})
    father_first_name = father_full_name.get('first', 'Unknown').strip()
    father_last_name = father_full_name.get('last', 'Unknown').strip()
    mother_full_name = parent_2.get('full_name', {})
    mother_first_name = mother_full_name.get('first', 'Unknown').strip()
    mother_last_name = mother_full_name.get('last', 'Unknown').strip()
    emergency_full_name = emergency_contact.get('name', {})
    emergency_contact_first_name = emergency_full_name.get('first', 'Unknown').strip()
    emergency_contact_last_name = emergency_full_name.get('last', 'Unknown').strip()
    
    father_string_name = sanitize_value(f"{father_first_name} {father_last_name}")
    mother_string_name = sanitize_value(f"{mother_first_name} {mother_last_name}")
    emergency_contact_string_name = sanitize_value(f"{emergency_contact_first_name} {emergency_contact_last_name}")
    
    def convert_dob(dob_str):
        try:
            dob = datetime.strptime(dob_str, "%m/%d/%Y")
            return dob.strftime("%Y-%m-%d")
        except Exception as e:
            return "NULL"
    
    sp_name = "dpinket_TC_QA.dbo.USP_UpdateTempStudentAuto" if input_data.get('InquiryID') else "dpinket_TC_QA.dbo.USP_InsertTempStudentAuto"
    
    base_query = f"""
    EXEC {sp_name}
        @StudentCount={student_count},
        @InquiryID={sanitize_value(input_data.get('InquiryID'))},
        @FormID=NULL,
        @SubmissionID=NULL,
        @GuardianFirstName={sanitize_value(input_data.get('GuardianFirstName'))},
        @GuardianLastName={sanitize_value(input_data.get('GuardianLastName'))},
        @FranchiseID={sanitize_value(template.get('franchise_id'))},
        @FranchiseName={sanitize_value(input_data.get('FranchiseName'))},
        @FranchiseEmail={sanitize_value(input_data.get('FranchiseEmail'))},
        @FranchiseAddress={sanitize_value(input_data.get('FranchiseAddress'))},
        @HomeAddress={sanitize_value(address_info.get('addr_line1', 'Unknown'))},
        @City={sanitize_value(address_info.get('city', 'Unknown'))},
        @State={sanitize_value(address_info.get('state', 'Unknown'))},
        @Zip={sanitize_value(address_info.get('postal', 'Unknown'))},
        @Street1={sanitize_value(address_info.get('addr_line1', 'Unknown'))},
        @FatherName={father_string_name},
        @FatherOccupation={sanitize_value(parent_1.get('occupation'))},
        @FatherEmployer={sanitize_value(parent_1.get('employer'))},
        @FatherCellPhone={sanitize_value(format_phone_number(parent_1.get('cell')))},
        @FatherEmail={sanitize_value(parent_1.get('email'))},
        @MotherName={mother_string_name},
        @MotherOccupation={sanitize_value(parent_2.get('occupation'))},
        @MotherEmployer={sanitize_value(parent_2.get('employer'))},
        @MotherCellPhone={sanitize_value(format_phone_number(parent_2.get('cell')))},
        @MotherEmail={sanitize_value(parent_2.get('email'))},
        @EmergencyContact1Type={sanitize_value(emergency_contact.get('type'))},
        @EmergencyContact1Name={emergency_contact_string_name},
        @EmergencyContact1Phone={sanitize_value(format_phone_number(emergency_contact.get('phone_number')))}
    """
    
    student_info_list = template.get('student_info', [])[0]
    for i in range(1, student_count + 1):
        student_key = f"student_{i}"
        student_info = student_info_list.get(student_key, {})
        name_info = student_info.get('name', {'FirstName': 'Unknown', 'LastName': 'Unknown'})
        dob_str = student_info.get('dob')
        dob_date = convert_dob(dob_str) if dob_str else "NULL"
        base_query += f""",
        @FirstName{i}={sanitize_value(name_info.get('FirstName', None))},
        @LastName{i}={sanitize_value(name_info.get('LastName', None))},
        @Grade{i}={sanitize_value(student_info.get('grade', None))},
        @Birthdate{i}={sanitize_value(dob_date)},
        @Age{i}={sanitize_value(str(student_info.get('age', None)))},
        @Question1String{i}={sanitize_value(student_info.get('academic_goals', {}).get('desired_status', None))},
        @Question2String{i}={sanitize_value(student_info.get('academic_goals', {}).get('attitude_school', None))},
        @Question3String{i}={sanitize_value(student_info.get('academic_goals', {}).get('improvement', None))},
        @Question4String{i}={sanitize_value(student_info.get('academic_goals', {}).get('concerns', None))},
        @Question5String{i}={sanitize_value(student_info.get('academic_goals', {}).get('motivation', None))},
        @AdditionalComments{i}={sanitize_value(student_info.get('academic_goals', {}).get('additional_notes', None))},
        @MedicalQuestion1Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('glasses', None))},
        @MedicalQuestion2Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('vision_problems', {}).get('issue', None))},
        @MedicalQuestion2Details{i}={sanitize_value(student_info.get('medical_info', {}).get('vision_problems', {}).get('details', None))},
        @MedicalQuestion3Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('hearing_problems', {}).get('issue', None))},
        @MedicalQuestion3Details{i}={sanitize_value(student_info.get('medical_info', {}).get('hearing_problems', {}).get('details', None))},
        @MedicalQuestion4Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('speech_impairments', {}).get('issue', None))},
        @MedicalQuestion4Details{i}={sanitize_value(student_info.get('medical_info', {}).get('speech_impairments', {}).get('details', None))},
        @MedicalQuestion5Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('early_childhood_health_issues', {}).get('issue', None))},
        @MedicalQuestion5Details{i}={sanitize_value(student_info.get('medical_info', {}).get('early_childhood_health_issues', {}).get('details', None))},
        @MedicalQuestion6Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('current_health_issues', {}).get('issue', None))},
        @MedicalQuestion6Details{i}={sanitize_value(student_info.get('medical_info', {}).get('current_health_issues', {}).get('details', None))},
        @MedicalQuestion7Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('current_medications', {}).get('issue', None))},
        @MedicalQuestion7Details{i}={sanitize_value(student_info.get('medical_info', {}).get('current_medications', {}).get('details', None))},
        @MedicalQuestion8Issue{i}={sanitize_value(student_info.get('medical_info', {}).get('psychological_evaluation', {}).get('has_evaluation', None))},
        @MedicalQuestion8Details{i}={sanitize_value(student_info.get('medical_info', {}).get('psychological_evaluation', {}).get('details', None))}
        """
    
    return base_query.strip()

##################################
# Database Connection & Execution#
##################################

# DB Connection Info (from environment variables)
server = 'localhost'
db_username = os.getenv('CRMSrvUs')
db_password = os.getenv('CRMSrvPs')
database = os.getenv('CRMSrvDb')

connection_string = f"mssql+pyodbc://{db_username}:{db_password}@{server}/{database}?driver=ODBC Driver 17 for SQL Server"
engine = create_engine(connection_string)
Session = sessionmaker(bind=engine)

def execute_sql_query(query):
    """Executes the given SQL query using SQLAlchemy engine with error handling and rollback."""
    connection = None
    trans = None
    try:
        connection = engine.connect()
        trans = connection.begin()
        # Wrap the query string with text() to make it executable.
        result = connection.execute(text(query))
        trans.commit()
        print("Query executed successfully.")
        return result
    except Exception as e:
        if trans:
            trans.rollback()
        print(f"Error executing query: {e}")
    finally:
        if connection:
            connection.close()

##################################
# Fetch Missing Input Data Query #
##################################

def fetch_missing_input_data(franchise_id, student1_first, student1_last):
    query = """
    SELECT InquiryID, GuardianFirstName, GuardianLastName, FranchiseName, FranchiseEmail, FranchiseAddress
    FROM dpinket_TC_QA.dbo.tblTempStudentAuto
    WHERE FranchiseID = :franchise_id
      AND FirstName = :first_name
      AND LastName = :last_name
    """
    try:
        connection = engine.connect()
        params = {
            "franchise_id": franchise_id,
            "first_name": student1_first,
            "last_name": student1_last
        }
        result = connection.execute(text(query), params)
        row = result.fetchone()
        connection.close()
        if row:
            # Convert the row (which is a tuple) to a dictionary using the keys
            row_dict = dict(zip(result.keys(), row))
            return {
                "InquiryID": row_dict["InquiryID"],
                "GuardianFirstName": row_dict["GuardianFirstName"],
                "GuardianLastName": row_dict["GuardianLastName"],
                "FranchiseName": row_dict["FranchiseName"],
                "FranchiseEmail": row_dict["FranchiseEmail"],
                "FranchiseAddress": row_dict["FranchiseAddress"]
            }
        else:
            return {}
    except Exception as e:
        print("Error fetching missing input data:", e)
        return {}

##################################
# Main Script Execution          #
##################################

def main():
    # build the Gmail service once
    service = get_gmail_service()
    # Retrieve unread emails.
    emails, mail = get_unread_emails()
    if not mail:
        print("No connection to mail server.")
        return
    if not emails:
        print("No unread emails found.")
        mail.close()
        mail.logout()
        return

    # Process the first unread email.
    eid, msg = emails[0]
    html_output = None
    html_found = False
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                try:
                    payload = part.get_payload(decode=True)
                    html_str = payload.decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html_str, 'html.parser')
                    html_output = soup.prettify()
                    html_found = True
                    break
                except Exception as e:
                    print(f"Error decoding HTML part: {e}")
    else:
        if msg.get_content_type() == 'text/html':
            try:
                payload = msg.get_payload(decode=True)
                html_str = payload.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_str, 'html.parser')
                html_output = soup.prettify()
                html_found = True
            except Exception as e:
                print(f"Error decoding HTML part: {e}")
    if not html_found:
        body = extract_email_body(msg)
        html_output = f"<html><body><pre>{body}</pre></body></html>"
    
    # Save HTML for debugging.
    with open("name.html", "w", encoding="utf-8") as f:
        f.write(html_output)
    print("HTML content written to name.html")
    
    # Parse HTML to build the mapping.
    mapping = parse_html_to_mapping(html_output)
    
    # Extract the web link and update franchise_id.
    web_link = extract_web_link(html_output)
    franchise = get_franchise_links(web_link)
    mapping["franchise_id"] = franchise.get("franchise_id")
    
    # Count non-empty student entries.
    student_count = count_students(mapping)
    
    # Extract Student 1's name from the mapping.
    student1 = mapping["student_info"][0]["student_1"]["name"]
    student1_first = student1.get("FirstName")
    student1_last = student1.get("LastName")
    franchise_id = mapping.get("franchise_id")
    
    # Fetch missing input data from the database.
    missing_data = fetch_missing_input_data(franchise_id, student1_first, student1_last)
    
    # Build input_data using the missing data if available.
    input_data = {
        "InquiryID": missing_data.get("InquiryID"),  # May be None if not found.
        "form_id": None,
        "submission_id": None,
        "GuardianFirstName": missing_data.get("GuardianFirstName", None),
        "GuardianLastName": missing_data.get("GuardianLastName", None),
        "FranchiseName": missing_data.get("FranchiseName", None),
        "FranchiseEmail": missing_data.get("FranchiseEmail", None),
        "FranchiseAddress": missing_data.get("FranchiseAddress", None)
    }
    
    # Generate SQL query.
    sql_query = generate_sql_query(input_data, mapping, student_count)
    print("Generated SQL Query:")
    print(sql_query)
    send_telegram_message(sql_query, log_bot, log_chat)
    
    # Execute the SQL query.
    result = execute_sql_query(sql_query)

    if result is not None:
        script_success_message = f"Script succeeded: SQL query executed successfully. {franchise_id}, {student1_first}, {student1_last}"
        send_telegram_message(script_success_message, auto_bot, auto_chat)
        mark_as_read(service, eid)
    else:
        script_error_message = f"Error Pulling from db - New Submission Script failed: Error executing SQL query. {franchise_id}, {student1_first}, {student1_last}"
        send_telegram_message(script_error_message, auto_bot, auto_chat)
        mark_as_read(service, eid)
    
    mail.close()
    mail.logout()
    
if __name__ == "__main__":
    main()
