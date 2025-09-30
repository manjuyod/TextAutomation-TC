import os
import time
import datetime
from dateutil.parser import parse
import requests
from sqlalchemy import create_engine
import Assessment2DataCollectionsVegasOnly

# Import any other necessary modules
import pandas as pd

###_____Constants____###
HOOK_VEGAS = os.getenv('ZapHookAssessGilVeg')
HOOK_CALI = os.getenv('ZapHookAssessCali')

###_________Input Validation_________##
def validate_input(data):
    required_fields = ['AutomationStage', 'FranchiseID', 'AssessmentDate', 'AssessmentTime', 'GuardianFirstName', 'StudentString']
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if 'FranchiseID' in data:
        try:
            data['FranchiseID'] = int(data['FranchiseID'])
        except ValueError:
            raise ValueError("FranchiseID must be a valid integer")

###_________Time Handling_________##
def get_timezone_offset(timezone_str):
    timezone_offsets = {
        'PST/PDT': {'standard': -8, 'dst': -7},
        'MST/MDT': {'standard': -7, 'dst': -6}
    }
    return timezone_offsets.get(timezone_str, {'standard': -8, 'dst': -7})

def is_dst(dt, timezone_str):
    dst_start = datetime.datetime(dt.year, 3, 8)
    dst_end = datetime.datetime(dt.year, 11, 1)
    while dst_start.weekday() != 6:
        dst_start += datetime.timedelta(days=1)
    while dst_end.weekday() != 6:
        dst_end += datetime.timedelta(days=1)
    return dst_start <= dt < dst_end

def format_greeting(franchise_id):
    utc_now = datetime.datetime.utcnow()
    timezone_str = get_timezone(franchise_id)
    offset_info = get_timezone_offset(timezone_str)
    if is_dst(utc_now, timezone_str):
        offset = datetime.timedelta(hours=offset_info['dst'])
    else:
        offset = datetime.timedelta(hours=offset_info['standard'])
    local_now = utc_now + offset
    hour = local_now.hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

def get_timezone(franchise_id):
    for franchise in franchise_info:
        if franchise[0] == franchise_id:
            return franchise[2]
    return 'PST/PDT'

def get_relative_day(assessment_date):
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    if assessment_date.date() == today:
        return "today"
    elif assessment_date.date() == tomorrow:
        return "tomorrow"
    else:
        return "on " + assessment_date.strftime("%A, %B %d")

###________Name String Handling________###
def ensure_list(data):
    try:
        if isinstance(data, str):
            delimiters = [', ', ',', '; ', ';']
            for delimiter in delimiters:
                if delimiter in data:
                    return [item.strip() for item in data.split(delimiter) if item.strip()]
            return [data.strip()] if data.strip() else []
        elif isinstance(data, list):
            return [item.strip() for item in data if item.strip()]
        else:
            raise ValueError("Unsupported data type for name processing.")
    except Exception as e:
        print(f"Error processing names: {e}")
        return []

def process_student_string(student_string):
    names = ensure_list(student_string)
    first_names = []
    for name in names:
        # Remove last names
        first_name = name.split()[0]  # Split on space and take the first part
        first_names.append(first_name)
    return first_names

def string_format_students(student_names):
    try:
        num_students = len(student_names)
        if num_students == 0:
            return "No students exist"
        elif num_students == 1:
            return f"{student_names[0]}"
        elif num_students == 2:
            return f"{student_names[0]} and {student_names[1]}"
        elif num_students >= 3:
            limited_names = student_names[:4]
            return ", ".join(f"{name}" for name in limited_names[:-1]) + f", and {limited_names[-1]}"
    except Exception as e:
        print(f"Error formatting student names: {e}")
        return "Error in student name formatting"

###_______ Franchise Info________###
franchise_info = [
    (6, 'Anthem', 'PST/PDT','https://tutoringclub.com/anthemnv/student-intake-form/','https://tutoringclub.com/anthemnv/assessment-payment-form/','11241 S Eastern Ave, Henderson, NV 89052',HOOK_VEGAS),
    (11, 'Green Valley', 'PST/PDT','https://tutoringclub.com/hendersonnv/student-intake-form/','https://tutoringclub.com/hendersonnv/assessment-payment-form/','2213 N Green Valley Pkwy #103, Henderson, NV 89014',HOOK_VEGAS),
    (15, 'North LV', 'PST/PDT','https://tutoringclub.com/northlasvegasnv/student-intake-form/','https://tutoringclub.com/northlasvegasnv/assessment-payment-form/','6120 N Decatur Blvd #102, North Las Vegas, NV 89031',HOOK_VEGAS),
    (16, 'Rhodes Ranch', 'PST/PDT','https://tutoringclub.com/rhodesranchnv/student-intake-form/','https://tutoringclub.com/rhodesranchnv/assessment-payment-form/','7315 S Rainbow Blvd #120, Las Vegas, NV 89113',HOOK_VEGAS),
    (60, 'Centennial', 'PST/PDT','https://tutoringclub.com/centennialnv/student-intake-form/','https://tutoringclub.com/centennialnv/assessment-payment-form/','6710 N Hualapai Way Suite 145, Las Vegas, NV 89149',HOOK_VEGAS),
    (19, 'Tutoring Club of Tustin', 'PST/PDT','https://tutoringclub.com/tustinca/student-intake-form/',None,'13721 Newport Avenue #7 Tustin, CA 92780 US',HOOK_CALI),
    (24,'North Fresno','PST/PDT','https://tutoringclub.com/fresnoca/student-intake-form/', 'https://tutoringclub.com/fresnoca/assessment-payment-form/','9423 North Fort Washington Road #106 Fresno, CA 93720',HOOK_CALI),
    (8,'Fountain Valley CA','PST/PDT','https://tutoringclub.com/fountain-valley-ca/student-intake-form/',None,'Our address is 9985 Ellis Ave, Fountain Valley, CA 92708.',HOOK_CALI),
    (20,'Clovis','PST/PDT','https://tutoringclub.com/clovisca/student-intake-form/',None,'Our address is 779 Herndon #105. We are on the northwest corner of Herndon and Clovis right next to the Starbucks.',HOOK_CALI),
    (87, 'Downey', 'PST/PDT','https://tutoringclub.com/downeyca/student-intake-form/',None,'8554 Firestone Blvd, Ste A Downey, CA 90241',HOOK_CALI)
    # Format: (FranchiseID, 'FranchiseName', 'timezonepair', 'AssessmentLink','PaymentLink', 'GoogleMapLink', 'WebhookLink')
    # Add other franchise entries as needed...
]

###________Text Selector__________###

def get_franchise_links(franchise_id):
    for franchise in franchise_info:
        if franchise[0] == franchise_id:
            return {
                'assessment_link': franchise[3],
                'payment_link': franchise[4],
                'map_link': franchise[5],
                'webhook_link':franchise[6]
            }
    return {'assessment_link': None, 'payment_link': None, 'map_link': None, 'webhook_link': None}  # Default if not found

def generate_message(automation_stage, parent_name, student_names, greeting, franchise_id, assessment_date, assessment_day, assessment_date_pretty, assessment_time):
    # Fetch the links based on the franchise ID
    links = get_franchise_links(franchise_id)
    relative_day = get_relative_day(assessment_date)
    assessment_date_info = f"{assessment_day}, {assessment_date_pretty} at {assessment_time}"

    # Nested helper function to capitalize names.
    def capitalize_name(name):
        # Capitalize each word in the name (e.g., "john doe" -> "John Doe")
        return ' '.join(word if word.lower() == "and" else word.capitalize() for word in name.split())
    
    # Capitalize the parent's and student's names.
    parent_name = capitalize_name(parent_name)
    student_names = capitalize_name(student_names)

    message_template = ""
    
    # Common greeting and introduction for Assessment Scheduled
    if franchise_id == 20:
        intro_message_one = f"""
Hi! {parent_name}! It's Katie from Tutoring Club Clovis — we're excited to get started with {student_names}! 

Their assessment is set for {assessment_date_info}.
"""
    elif franchise_id ==8:
        intro_message_one = f"""
Hi {parent_name}! It's Huy from Tutoring Club — we're excited to get started with {student_names}! 

Their assessment is set for {assessment_date_info}.
"""
    else:
        intro_message_one = f"""
{greeting} {parent_name},

Thank you for choosing Tutoring Club as a partner in your child's educational journey. We are delighted to have the opportunity to contribute to {student_names}'s academic progress.

Your child's assessment is set for {assessment_date_info}.
"""
    # Common greeting and introduction for Assessment Morning
    if franchise_id == 20:
        intro_message_two = f"""
Hi {parent_name}! It's Katie from Tutoring Club Clovis, just confirming your visit with us {relative_day}.

{student_names}’s assessment is scheduled for {assessment_time}.
"""
    elif franchise_id == 8:
        intro_message_two = f"""
Hi {parent_name}! It's Huy from Tutoring Club , just confirming your visit with us {relative_day}.

Their assessment is set for {assessment_date_info}.
"""
    else:
        intro_message_two = f"""
{greeting} {parent_name},

This is Tutoring Club. I'm reaching out to confirm our appointment scheduled for {student_names} {relative_day}, at {assessment_time}.
"""
    # Optional lines depending on link availability
    if franchise_id in (8, 20):
        assessment_link_message_one = f"""
If you haven't already, you can fill out our student info form here:
{links['assessment_link']}
""" if links['assessment_link'] else ""
        
    else:
        assessment_link_message_one = f"""
For convenience, you may complete our Student Information form with the following link: 
{links['assessment_link']}
""" if links['assessment_link'] else ""
    
    if franchise_id in (8, 20):
        assessment_link_message_two = f"""
If you haven't already, you can fill out our student info form here:
{links['assessment_link']}
""" if links['assessment_link'] else ""
    else:
        assessment_link_message_two = f"""
If you haven't already, you may complete our Student Information form with the following link: 
{links['assessment_link']}
""" if links['assessment_link'] else ""

    payment_link_message_one = f"""
Also for your convenience, you may pay for the Assessment by clicking on the following link:
{links['payment_link']}
""" if links['payment_link'] else ""
    
    payment_link_message_two = f"""
You may also pay for the Assessment by clicking on the following link:
{links['payment_link']}
""" if links['payment_link'] else ""

    if franchise_id in (8, 20):
        map_link_message = f"""
{links['map_link']}
""" if links['map_link'] else ""
        
    else:
        map_link_message = f"""
For your convenience, please find the location of our center here: 
{links['map_link']}
""" if links['map_link'] else ""

    # Closing statement
    if franchise_id in (8, 20):
        closing_message_one ="""
Let me know if you have any questions before then — we're looking forward to meeting you both!
"""
    else:
        closing_message_one = """
We look forward to creating a personalized academic plan together.

If you have any questions feel free to reach out. 

Thank You!
"""
    if franchise_id in (8, 20):
        closing_message_two ="""
Looking forward to seeing you both soon! Please reply to confirm or let me know if you have any questions.
"""
    else:
        closing_message_two = """
Please text back to confirm your appointment.
"""

    if automation_stage == "Assessment1":
        message_template = intro_message_one + assessment_link_message_one + payment_link_message_one + closing_message_one
    elif automation_stage == "Assessment2":
        message_template = intro_message_two + assessment_link_message_two + payment_link_message_two + map_link_message + closing_message_two
    else:
        message_template = "An unexpected error occurred with the automation stage."

    return message_template.strip()

###________Send to Zapier Function________###
def send_to_zapier(message, input_data, franchise_id):
    # Get the franchise links (including the webhook) based on the provided franchise_id
    links = get_franchise_links(franchise_id)

    zapier_webhook_url = links['webhook_link']
    if not zapier_webhook_url:
        print("Zapier webhook URL is not set.")
        return
    payload = {
        'message': message,
        'AssessmentPhone': input_data['AssessmentPhone'],
        'FranchiseID': input_data['FranchiseID'],
        # Add other fields if necessary
    }
    try:
        response = requests.post(zapier_webhook_url, json=payload)
        response.raise_for_status()
        print(f"Message sent to Zapier - {input_data['GuardianFirstName']} for phone {input_data['AssessmentPhone']}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to Zapier: {e}")

###________Process Each Row________###
def process_row(row):
    input_data = {
        "AutomationStage": row['AutomationStage'],
        "FranchiseID": row['FranchiseID'],
        "AssessmentDate": row['AssessmentDate'],
        "AssessmentTime": row['AssessmentTime'],
        "AssessmentEmail": row['AssessmentEmail'],
        "AssessmentPhone": row['AssessmentPhone'],
        "GuardianFirstName": row['GuardianFirstName'],
        "StudentString": row['StudentString']
    }
    try:
        validate_input(input_data)
    except ValueError as e:
        print(f"Skipping row due to validation error: {e}")
        return
    # Parsing date and time
    assessment_date = parse(str(input_data['AssessmentDate']))
    assessment_day = assessment_date.strftime('%A')
    assessment_date_pretty = assessment_date.strftime('%B %d')
    assessment_time = parse(str(input_data['AssessmentTime'])).strftime('%I:%M %p')
    # Determine the appropriate greeting based on time and franchise
    greeting = format_greeting(input_data['FranchiseID'])
    # Process StudentString to get first names
    student_names_list = process_student_string(input_data['StudentString'])
    student_names_formatted = string_format_students(student_names_list)
    # Generate the message
    message = generate_message(
        automation_stage=input_data['AutomationStage'],
        parent_name=input_data['GuardianFirstName'],
        student_names=student_names_formatted,
        greeting=greeting,
        franchise_id=input_data['FranchiseID'],
        assessment_date=assessment_date,
        assessment_day=assessment_day,
        assessment_date_pretty=assessment_date_pretty,
        assessment_time=assessment_time
    )
    # Send message via Zapier webhook
    send_to_zapier(message, input_data, input_data['FranchiseID'])
    # Optional: Print the message for debugging
    print("Message sent:")
    #print(message)
    #print("-----")

###________Main Function________###
def main():
    # Create the engine (assuming environment variables are set)
    server = 'localhost'
    username = os.getenv('CRMSrvUs')
    password = os.getenv('CRMSrvPs')
    database = os.getenv('CRMSrvDb')
    connection_string = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC Driver 17 for SQL Server"
    engine = create_engine(connection_string)
    # Fetch the DataFrame from Assessment2DataCollections
    df = Assessment2DataCollectionsVegasOnly.fetch_assessment_data(engine)
    if df.empty:
        print("No new assessments to process.")
        return
    for index, row in df.iterrows():
        process_row(row)
        time.sleep(2)

if __name__ == "__main__":
    main()
