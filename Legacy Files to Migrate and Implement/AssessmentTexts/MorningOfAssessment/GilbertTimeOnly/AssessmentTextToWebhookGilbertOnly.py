import os
import time
import datetime
from dateutil.parser import parse
import requests
from sqlalchemy import create_engine
import Assessment2DataCollectionsGilbertOnly

# Import any other necessary modules
import pandas as pd

###_____Constants____###
HOOK_VEGAS = os.getenv('ZapHookAssessGilVeg')

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
    (57, 'Gilbert', 'MST/MDT','https://tutoringclub.com/gilbertaz/student-intake-form/','https://tutoringclub.com/gilbertaz/assessment-payment-form/','3305 E Williams Field Rd #102, Gilbert, AZ 85295',HOOK_VEGAS)
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
                'map_link': franchise[5]
            }
    return {'assessment_link': None, 'payment_link': None, 'map_link': None}  # Default if not found

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
    
    # Common greeting and introduction
    intro_message_one = f"""
{greeting} {parent_name},

Thank you for choosing Tutoring Club as a partner in your child's educational journey. We are delighted to have the opportunity to contribute to {student_names}'s academic progress.

Your child's assessment is set for {assessment_date_info}.
"""
    intro_message_two = f"""
{greeting} {parent_name},

This is Tutoring Club. I'm reaching out to confirm our appointment scheduled for {student_names} {relative_day}, at {assessment_time}.
"""
    # Optional lines depending on link availability
    assessment_link_message_one = f"""
For convenience, you may complete our Student Information form with the following link: 
{links['assessment_link']}
""" if links['assessment_link'] else ""
    
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

    map_link_message = f"""
For your convenience, please find the location of our center here: 
{links['map_link']}
""" if links['map_link'] else ""

    # Closing statement
    closing_message_one = """
We look forward to creating a personalized academic plan together.

If you have any questions feel free to reach out. 

Thank You!
"""
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
    send_to_zapier(message, input_data)
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
    df = Assessment2DataCollectionsGilbertOnly.fetch_assessment_data(engine)
    if df.empty:
        print("No new assessments to process.")
        return
    for index, row in df.iterrows():
        process_row(row)
        time.sleep(2)

if __name__ == "__main__":
    main()
