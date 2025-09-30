"""
AssessmentScheduledToWebhookOnly.py
Purpose: Main function to orchestrate:
         1) Compare SQL Server data vs. local SQLite cache
         2) Delete extraneous rows from local cache
         3) Insert new rows into local cache
         4) Loop through all rows where IsText = 'No' and send text
         5) Update local cache marking text-sent rows as IsText='Yes'
"""

import sys
import os
import time
import datetime
from dateutil.parser import parse
import requests
from sqlalchemy import create_engine

# Adjust paths if needed
module_folder = os.path.abspath(
    "C:\\Users\\Administrator\\Desktop\\Scripts\\reporting-v1\\ReportScripts\\ZapierAutomation\\MeetingTexts\\NewMeetings"
)
sys.path.append(module_folder)

import Meeting1DataCollectionsOnly
import Meeting1SQLiteFunctions

import pandas as pd

###_____Constants____###
HOOK_VEGAS = os.getenv('ZapHookMeetingGilVeg')
HOOK_CALI = os.getenv('ZapHookMeetingCali')

###_____Input Validation_____###
def check_grade(grade):
    valid_grades = ['Pre-K', 'K', '1st', '2nd', '3rd', '4th', '5th']
    return grade in valid_grades

def validate_input(data):
    required_fields = ['AutomationStage', 'FranchiseID', 'MeetingDate', 'MeetingTime', 'GuardianFirstName', 'StudentString']
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    if 'FranchiseID' in data:
        try:
            data['FranchiseID'] = int(data['FranchiseID'])
        except ValueError:
            raise ValueError("FranchiseID must be a valid integer")

###_____Time & Daylight Saving_____###
def get_timezone_offset(timezone_str):
    timezone_offsets = {
        'PST/PDT': {'standard': -8, 'dst': -7},
        'MST/MDT': {'standard': -7, 'dst': -6}
    }
    return timezone_offsets.get(timezone_str, {'standard': -8, 'dst': -7})

def is_dst(dt, timezone_str):
    # Simplistic DST approach 
    dst_start = datetime.datetime(dt.year, 3, 8)
    dst_end = datetime.datetime(dt.year, 11, 1)
    while dst_start.weekday() != 6:  # Move to 2nd Sunday in March
        dst_start += datetime.timedelta(days=1)
    while dst_end.weekday() != 6:  # Move to 1st Sunday in November
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
    # Adjust to your real data
    for franchise in franchise_info:
        if franchise[0] == franchise_id:
            return franchise[2]
    return 'PST/PDT'

def get_relative_day(meeting_date):
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    if meeting_date.date() == today:
        return "today"
    elif meeting_date.date() == tomorrow:
        return "tomorrow"
    else:
        return "on " + meeting_date.strftime("%A, %B %d")

###_____Name String Handling_____###
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
        first_name = name.split()[0]  # Take the first part
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
        else:
            limited_names = student_names[:4]
            return ", ".join(f"{name}" for name in limited_names[:-1]) + f", and {limited_names[-1]}"
    except Exception as e:
        print(f"Error formatting student names: {e}")
        return "Error in student name formatting"

###_______ Parent Handling Function_____________###
def resolve_parent_names(input_data):
    guardian_name = input_data.get('GuardianFirstName', '').strip() if input_data.get('GuardianFirstName', '') else ''

    parent1_name = input_data.get('Parent1Name', '')
    parent1_name = parent1_name.strip() if parent1_name else ''

    parent2_name = input_data.get('Parent2Name', '')
    parent2_name = parent2_name.strip() if parent2_name else ''

    parent1_first_name = parent1_name.split()[0].strip() if parent1_name else ''
    parent2_first_name = parent2_name.split()[0].strip() if parent2_name else ''

    primary_parent = None
    secondary_parent = ''
    guardian_default = guardian_name
    if not parent1_first_name and not parent2_first_name:
        primary_parent = guardian_default
    elif parent1_first_name == parent2_first_name:
        primary_parent = guardian_default
        secondary_parent = ''
    elif parent1_first_name.lower() in {"n/a", "na", "not available"}:
        secondary_parent = guardian_default
        primary_parent = ''
    elif parent2_first_name.lower() in {"n/a", "na", "not available"}:
        primary_parent = guardian_default
        secondary_parent = ''
    elif guardian_name.lower() in parent1_first_name.lower():
        primary_parent = parent1_first_name
        secondary_parent = f" and {parent2_first_name}" if parent2_first_name else ''
    elif guardian_name.lower() in parent2_first_name.lower():
        primary_parent = parent2_first_name
        secondary_parent = f" and {parent1_first_name}" if parent1_first_name else ''
    else:
        primary_parent = guardian_default
        secondary_parent = ''
    return primary_parent, secondary_parent, guardian_default

###_____Franchise Info_____###
franchise_info = [
    (1, 'Test', 'PST/PDT', None,None, 'NON LOL',HOOK_VEGAS),
    (57, 'Gilbert', 'MST/MDT',None,None,'3305 E Williams Field Rd #102, Gilbert, AZ 85295',HOOK_VEGAS),
    (6, 'Anthem', 'PST/PDT',None,None,'11241 S Eastern Ave, Henderson, NV 89052',HOOK_VEGAS),
    (11, 'Green Valley', 'PST/PDT',None,None,'2213 N Green Valley Pkwy #103, Henderson, NV 89014',HOOK_VEGAS),
    (15, 'North LV', 'PST/PDT',None,None,'6120 N Decatur Blvd #102, North Las Vegas, NV 89031',HOOK_VEGAS),
    (16, 'Rhodes Ranch', 'PST/PDT',None,None,'7315 S Rainbow Blvd #120, Las Vegas, NV 89113',HOOK_VEGAS),
    (60, 'Centennial', 'PST/PDT',None,None,'6710 N Hualapai Way Suite 145, Las Vegas, NV 89149',HOOK_VEGAS),
    (24,'North Fresno','PST/PDT',None,None,'9423 North Fort Washington Road #106 Fresno, CA 93720',HOOK_CALI),
    (19,'Tutoring Club of Tustin','PST/PDT',None,None,'13721 Newport Avenue #7 Tustin, CA 92780 US',HOOK_CALI),
    (8,'Fountain Calley CA','PST/PDT',None,None,'9985 Ellis Ave, Fountain Valley, CA 92708',HOOK_CALI),
    (20,'Clovis','PST/PDT',None,None,'779 Herndon #105. We are on the northwest corner of Herndon and Clovis right next to the Starbucks.',HOOK_CALI),
    (87,'Downey','PST/PDT',None,None,'8554 Firestone Blvd, Ste A Downey, CA 90241',HOOK_CALI)
    # Format: (FranchiseID, 'FranchiseName', 'timezonepair', 'AssessmentLink','PaymentLink', 'GoogleMapLink', 'WebhookLink')
    # Add other franchise entries as needed...
]

###_____Text Selector_____###
def get_franchise_links(franchise_id):
    for franchise in franchise_info:
        if franchise[0] == franchise_id:
            return {
                'assessment_link': franchise[3],
                'payment_link': franchise[4],
                'map_link': franchise[5],
                'webhook_link': franchise[6]
            }
    return {'assessment_link': None, 'payment_link': None, 'map_link': None, 'webhook_link': None}

def generate_message(automation_stage, primary_parent, secondary_parent, guardian_default, student_names, greeting, grade, meeting_date, meeting_day, meeting_date_pretty, meeting_time, franchise_id):
    relative_day = get_relative_day(meeting_date)
    meeting_date_info = f"{meeting_day}, {meeting_date_pretty} at {meeting_time}"
    message_template = ""
    grade_validity = check_grade(grade)

    # Nested helper function to capitalize names.
    def capitalize_name(name):
        # Capitalize each word in the name (e.g., "john doe" -> "John Doe")
        return ' '.join(word if word.lower() == "and" else word.capitalize() for word in name.split())
    
    # Capitalize the parent's and student's names.
    primary_parent = capitalize_name(primary_parent)
    secondary_parent = capitalize_name(secondary_parent)
    guardian_default = capitalize_name(guardian_default)
    student_names = capitalize_name(student_names)

    laptop_message = f"""
Please have {student_names} bring their Chromebook or laptop for the meeting, as we will log into their school portals.
""" if not grade_validity else ""
    closing_message_one = """
Thank you!
"""
    closing_message_two = """
Please text back to confirm your appointment. Thank you!
"""
    if automation_stage == "Meeting1":
        if franchise_id not in (8, 20):
            if primary_parent and secondary_parent:
                message_template = f"""
{greeting} {primary_parent},

This is Tutoring Club. Thank you for allowing us to assess {student_names}. I have scheduled our enrollment meeting with you {secondary_parent} on {meeting_date_info} to discuss {student_names}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.
""" + closing_message_one
            else:
                message_template = f"""
{greeting} {guardian_default},

This is Tutoring Club. Thank you for allowing us to assess {student_names}. I have scheduled our enrollment meeting with you on {meeting_date_info} to discuss {student_names}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.
""" + closing_message_one
        elif franchise_id == 20:
            message_template = f"""
Hi {guardian_default}! It's Katie from Tutoring Club Clovis.

Thank you for bringing {student_names} in for their assessment! I've scheduled a follow-up meeting with you on {meeting_date_info} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""
        elif franchise_id == 8:
            message_template = f"""
Hi {guardian_default}! It's Huy from Tutoring Club.

Thank you for bringing {student_names} in for their assessment! I've scheduled a follow-up meeting with you on {meeting_date_info} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""

        else:
            message_template = f"""
Hi {guardian_default}! It's Tutoring Club.

Thank you for bringing {student_names} in for their assessment! I've scheduled a follow-up meeting with you on {meeting_date_info} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""
    elif automation_stage == "Meeting2":
        if primary_parent and secondary_parent:
            message_template = f"""
{greeting} {primary_parent},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you {secondary_parent} to discuss {student_names}’s academic plan, our different tuition options, and scheduling.
""" + laptop_message + closing_message_two
        else:
            message_template = f"""
{greeting} {guardian_default},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you to discuss {student_names}’s academic plan, our different tuition options, and scheduling.
""" + laptop_message + closing_message_two
    else:
        message_template = "An unexpected error occurred with the automation stage."
    return message_template.strip()

###_____Send to Zapier_____###
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
        print(f"Message sent to Zapier - {input_data['GuardianFirstName']} (Phone: {input_data['AssessmentPhone']})")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to Zapier: {e}")

###_____Process Each Row (Send Text)_____###
def process_row(row):
    """
    Builds the message from the given row, sends it via Zapier,
    and updates IsText = 'Yes' if successful.
    Returns True on success, False on failure.
    """
    # ----- 1) Build your data dictionary from row -----
    input_data = {
        "AutomationStage": row["AutomationStage"],
        "FranchiseID": row["FranchiseID"],
        "MeetingDate": row["MeetingDate"],
        "MeetingTime": row["MeetingTime"],
        "AssessmentEmail": row["AssessmentEmail"],
        "AssessmentPhone": row["AssessmentPhone"],
        "GuardianFirstName": row["GuardianFirstName"],
        "StudentString": row["StudentString"],
        "Grade": row["Grade"],
        "Parent1Name": row["Parent1Name"],
        "Parent2Name": row["Parent2Name"],
    }
    
    try:
        # ----- 2) Validate the input -----
        validate_input(input_data)
        
        # ----- 3) Parse the date/time for the meeting -----
        meeting_date = parse(str(input_data["MeetingDate"]))
        meeting_day = meeting_date.strftime("%A")
        meeting_date_pretty = meeting_date.strftime("%B %d")
        meeting_time = parse(str(input_data["MeetingTime"])).strftime("%I:%M %p")

        # ----- 4) Generate the greeting, parent names, and final message -----
        greeting = format_greeting(input_data["FranchiseID"])
        primary_parent, secondary_parent, guardian_default = resolve_parent_names(input_data)
        student_first_names = process_student_string(input_data["StudentString"])
        student_names_formatted = string_format_students(student_first_names)
        
        # ----- 5) Generate the text message to send -----
        message = generate_message(
            input_data["AutomationStage"],
            primary_parent,
            secondary_parent,
            guardian_default,
            student_names_formatted,
            greeting,
            input_data["Grade"],
            meeting_date,
            meeting_day,
            meeting_date_pretty,
            meeting_time,
            input_data['FranchiseID']
        )
        
        # ----- 6) Send the message to Zapier -----
        send_to_zapier(message, input_data, input_data['FranchiseID'])
        
        # ----- 7) If we got here with no exceptions, mark IsText = 'Yes' -----
        Meeting1SQLiteFunctions.update_meeting_cache(
            Meeting1SQLiteFunctions.engine,
            [row["InquiryID"]]
        )
        
        # Return True to indicate success
        return True
    
    except Exception as e:
        # If anything went wrong, log the error and return False
        print(f"Error processing row (InquiryID={row['InquiryID']}): {e}")
        return False

###_____Main Function_____###
def main():
    # 1) Fetch the DataFrame from SQL Server
    print("Fetching data from SQL Server...")
    df_server = Meeting1DataCollectionsOnly.fetch_meeting_data(
        Meeting1DataCollectionsOnly.engine
    )

    # 2) Fetch the Cache from SQLite
    print("Fetching data from local SQLite cache...")
    df_cache = Meeting1SQLiteFunctions.select_meeting_cache(
        Meeting1SQLiteFunctions.engine
    )

    if df_server.empty and df_cache.empty:
        print("No data in server or cache. Nothing to do.")
        return

    server_ids = set(df_server['InquiryID'].unique())
    cache_ids = set(df_cache['InquiryID'].unique())

    # --- STEP A: Handle truly extraneous rows (IDs not in server at all) ---
    extraneous_ids = cache_ids - server_ids
    if extraneous_ids:
        print(f"Deleting {len(extraneous_ids)} extraneous records from cache.")
        Meeting1SQLiteFunctions.delete_meeting_cache(
            Meeting1SQLiteFunctions.engine,
            extraneous_ids
        )

    # --- STEP B: Handle "reschedules" for matching InquiryIDs ---
    # 1) Find intersection
    intersect_ids = server_ids & cache_ids
    if intersect_ids:
        df_server_intersect = df_server[df_server['InquiryID'].isin(intersect_ids)]
        df_cache_intersect = df_cache[df_cache['InquiryID'].isin(intersect_ids)]

        # 2) Convert date/time columns to combined datetime so we can compare
        def parse_meeting_datetime(df, date_col, time_col):
            combined = []
            for _, row in df.iterrows():
                try:
                    dt_date = pd.to_datetime(str(row[date_col])).date()
                    dt_time = pd.to_datetime(str(row[time_col])).time()
                    combined.append(datetime.datetime.combine(dt_date, dt_time))
                except Exception:
                    combined.append(None)
            return combined

        df_server_intersect = df_server_intersect.copy()
        df_cache_intersect = df_cache_intersect.copy()

        df_server_intersect["MeetingDatetime"] = parse_meeting_datetime(
            df_server_intersect, "MeetingDate", "MeetingTime"
        )
        df_cache_intersect["MeetingDatetime"] = parse_meeting_datetime(
            df_cache_intersect, "MeetingDate", "MeetingTime"
        )

        # 3) Merge on InquiryID to compare times
        merged = pd.merge(
            df_server_intersect[["InquiryID", "MeetingDatetime"]],
            df_cache_intersect[["InquiryID", "MeetingDatetime"]],
            on="InquiryID",
            suffixes=("_srv", "_cache")
        )

        # 4) Any difference => rescheduled
        rescheduled_ids = []
        for _, row in merged.iterrows():
            srv_dt = row["MeetingDatetime_srv"]
            cache_dt = row["MeetingDatetime_cache"]
            if srv_dt != cache_dt:
                rescheduled_ids.append(row["InquiryID"])

        # 5) Delete rescheduled from cache
        if rescheduled_ids:
            print(f"Found {len(rescheduled_ids)} reschedules. Deleting them from cache.")
            Meeting1SQLiteFunctions.delete_meeting_cache(
                Meeting1SQLiteFunctions.engine, rescheduled_ids
            )

    # --- STEP C: Now that extraneous + rescheduled rows are removed,
    #             insert rows that are missing from the cache
    df_cache_after_delete = Meeting1SQLiteFunctions.select_meeting_cache(
        Meeting1SQLiteFunctions.engine
    )
    cache_ids_after_delete = set(df_cache_after_delete['InquiryID'].unique())

    new_ids = server_ids - cache_ids_after_delete
    if new_ids:
        df_new = df_server[df_server['InquiryID'].isin(new_ids)]
        print(f"Inserting {len(df_new)} new records into cache (including reschedules).")
        Meeting1SQLiteFunctions.insert_meeting_cache(
            Meeting1SQLiteFunctions.engine,
            df_new
        )

    # --- STEP D: Fetch the updated cache & text all rows with IsText='No'
    df_cache_current = Meeting1SQLiteFunctions.select_meeting_cache(
        Meeting1SQLiteFunctions.engine
    )
    df_to_text = df_cache_current[df_cache_current["IsText"] == "No"]
    
    if df_to_text.empty:
        print("No rows require texting (IsText = 'No').")
        return
    
    print(f"Sending texts for {len(df_to_text)} rows...")
    for idx, row in df_to_text.iterrows():
        success = process_row(row)
        if not success:
            print(f"Failed to send text for InquiryID={row['InquiryID']}.")
        # Optional sleep to avoid hammering the webhook
        time.sleep(2)

if __name__ == "__main__":
    main()