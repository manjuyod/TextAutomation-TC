import os
import time
import datetime
from dateutil.parser import parse
import requests
from sqlalchemy import create_engine
import Meeting2DataCollectionsTestOnly

# Import any other necessary modules
import pandas as pd

###_____Constants____###
HOOK_VEGAS = os.getenv('ZapHookMeetingGilVeg')

###_________Input Validation_________##
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

def get_relative_day(meeting_date):
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    if meeting_date.date() == today:
        return "today"
    elif meeting_date.date() == tomorrow:
        return "tomorrow"
    else:
        return "on " + meeting_date.strftime("%A, %B %d")

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

###________Text Selector__________###
def get_franchise_links(franchise_id):
    for franchise in franchise_info:
        if franchise[0] == franchise_id:
            return {
                'assessment_link': franchise[3],
                'payment_link': franchise[4],
                'map_link': franchise[5]
            }
    return {'assessment_link': None, 'payment_link': None, 'map_link': None}  # Default if not found

def generate_message(automation_stage, primary_parent, secondary_parent, guardian_default, student_names, greeting, franchise_id, grade, meeting_date, meeting_day, meeting_date_pretty, meeting_time):
    links = get_franchise_links(franchise_id)
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
Please have {student_names} bring their Chromebook or laptop for the meeting, as we will log into their Canvas and Infinite Campus accounts.
""" if not grade_validity else ""
    closing_message_one = """
Thank you!
"""
    map_link_message = f"""
For your convenience, please find the location of our center here: 
{links['map_link']}
""" if links['map_link'] else ""
    
    closing_message_two = """
Please text back to confirm your appointment. Thank you!
"""
    if automation_stage == "Meeting1":
        if primary_parent and secondary_parent:
            message_template = f"""
{greeting} {primary_parent},

This is Tutoring Club. Thank you for allowing us to assess {student_names}. I have scheduled our enrollment meeting with you {secondary_parent} on {meeting_date_info} to discuss {student_names}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.
""" + map_link_message + closing_message_one
        else:
            message_template = f"""
{greeting} {guardian_default},

This is Tutoring Club. Thank you for allowing us to assess {student_names}. I have scheduled our enrollment meeting with you on {meeting_date_info} to discuss {student_names}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.
""" + map_link_message + closing_message_one
    elif automation_stage == "Meeting2":
        if primary_parent and secondary_parent:
            message_template = f"""
{greeting} {primary_parent},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you {secondary_parent} to discuss {student_names}’s academic plan, our different tuition options, and scheduling.
""" + laptop_message + map_link_message + closing_message_two
        else:
            message_template = f"""
{greeting} {guardian_default},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you to discuss {student_names}’s academic plan, our different tuition options, and scheduling.
""" + laptop_message + map_link_message + closing_message_two
    else:
        message_template = "An unexpected error occurred with the automation stage."
    return message_template.strip()

###_______ Franchise Info________###
franchise_info = [
    (1, 'Test', 'PST/PDT', 'https://form.jotform.com/anthemnv/TutoringClubAnthmStudentInformation', 'https://form.jotform.com/241565841262154', 'https://g.co/kgs/T1szoKY'),
    # Add other franchise entries as needed...
]

###________Send to Zapier Function________###
def send_to_zapier(message, input_data):
    zapier_webhook_url = HOOK_VEGAS
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
        "MeetingDate": row['MeetingDate'],
        "MeetingTime": row['MeetingTime'],
        "AssessmentEmail": row['AssessmentEmail'],
        "AssessmentPhone": row['AssessmentPhone'],
        "GuardianFirstName": row['GuardianFirstName'],
        "StudentString": row['StudentString'],
        "Grade": row['Grade'],
        "Parent1Name": row['Parent1Name'],
        "Parent2Name": row['Parent2Name']
    }
    try:
        validate_input(input_data)
    except ValueError as e:
        print(f"Skipping row due to validation error: {e}")
        return
    # Parsing date and time
    meeting_date = parse(str(input_data['MeetingDate']))
    meeting_day = meeting_date.strftime('%A')
    meeting_date_pretty = meeting_date.strftime('%B %d')
    meeting_time = parse(str(input_data['MeetingTime'])).strftime('%I:%M %p')
    # Determine the appropriate greeting based on time and franchise
    greeting = format_greeting(input_data['FranchiseID'])
    # Resolve parent names
    primary_parent, secondary_parent, guardian_default = resolve_parent_names(input_data)
    # Process StudentString to get first names
    student_first_names = process_student_string(input_data['StudentString'])
    student_names_formatted = string_format_students(student_first_names)
    # Process FranchiseID
    franchise_id = input_data['FranchiseID']
    # Generate the message
    message = generate_message(
        input_data['AutomationStage'],
        primary_parent,
        secondary_parent,
        guardian_default,
        student_names_formatted,
        greeting,
        franchise_id,
        input_data['Grade'],
        meeting_date,
        meeting_day,
        meeting_date_pretty,
        meeting_time
    )
    # Send message via Zapier webhook
    send_to_zapier(message, input_data)

###________Main Function________###
def main():
    # Create the engine (assuming environment variables are set)
    server = 'localhost'
    username = os.getenv('CRMSrvUs')
    password = os.getenv('CRMSrvPs')
    database = os.getenv('CRMSrvDb')
    connection_string = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC Driver 17 for SQL Server"
    engine = create_engine(connection_string)
    # Fetch the DataFrame from Meeting2DataCollections
    df = Meeting2DataCollectionsTestOnly.fetch_meeting_data(engine)
    if df.empty:
        print("No new meetings to process.")
        return
    for index, row in df.iterrows():
        process_row(row)
        time.sleep(2)

if __name__ == "__main__":
    main()
