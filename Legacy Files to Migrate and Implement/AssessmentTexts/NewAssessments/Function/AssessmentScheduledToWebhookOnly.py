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
    "C:\\Users\\Administrator\\Desktop\\Scripts\\reporting-v1\\ReportScripts\\ZapierAutomation\\AssessmentTexts\\NewAssessments"
)
sys.path.append(module_folder)

import Assessment1DataCollectionsOnly
import Assessment1SQLiteFunctions

import pandas as pd

###_____Constants____###
HOOK_VEGAS = os.getenv('ZapHookAssessGilVeg')
HOOK_CALI = os.getenv('ZapHookAssessCali')

###_____Input Validation_____###
def validate_input(data):
    required_fields = [
        'AutomationStage', 'FranchiseID', 'AssessmentDate',
        'AssessmentTime', 'GuardianFirstName', 'StudentString'
    ]
    missing_fields = [
        field for field in required_fields 
        if field not in data or data[field] is None
    ]
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

def get_relative_day(assessment_date):
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    if assessment_date.date() == today:
        return "today"
    elif assessment_date.date() == tomorrow:
        return "tomorrow"
    else:
        return "on " + assessment_date.strftime("%A, %B %d")

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

###_____Franchise Info_____###
franchise_info = [
    (1, 'Test', 'PST/PDT', None,None, 'NON LOL',HOOK_VEGAS),
    (57, 'Gilbert', 'MST/MDT','https://tutoringclub.com/gilbertaz/student-intake-form/','https://tutoringclub.com/gilbertaz/assessment-payment-form/','3305 E Williams Field Rd #102, Gilbert, AZ 85295',HOOK_VEGAS),
    (6, 'Anthem', 'PST/PDT','https://tutoringclub.com/anthemnv/student-intake-form/','https://tutoringclub.com/anthemnv/assessment-payment-form/','11241 S Eastern Ave, Henderson, NV 89052',HOOK_VEGAS),
    (11, 'Green Valley', 'PST/PDT','https://tutoringclub.com/hendersonnv/student-intake-form/','https://tutoringclub.com/hendersonnv/assessment-payment-form/','2213 N Green Valley Pkwy #103, Henderson, NV 89014',HOOK_VEGAS),
    (15, 'North LV', 'PST/PDT','https://tutoringclub.com/northlasvegasnv/student-intake-form/','https://tutoringclub.com/northlasvegasnv/assessment-payment-form/','6120 N Decatur Blvd #102, North Las Vegas, NV 89031',HOOK_VEGAS),
    (16, 'Rhodes Ranch', 'PST/PDT','https://tutoringclub.com/rhodesranchnv/student-intake-form/','https://tutoringclub.com/rhodesranchnv/assessment-payment-form/','7315 S Rainbow Blvd #120, Las Vegas, NV 89113',HOOK_VEGAS),
    (19, 'Tutoring Club of Tustin', 'PST/PDT','https://tutoringclub.com/tustinca/student-intake-form/',None,'13721 Newport Avenue #7 Tustin, CA 92780 US',HOOK_CALI),
    (60, 'Centennial', 'PST/PDT','https://tutoringclub.com/centennialnv/student-intake-form/','https://tutoringclub.com/centennialnv/assessment-payment-form/','6710 N Hualapai Way Suite 145, Las Vegas, NV 89149',HOOK_VEGAS),
    (24,'North Fresno','PST/PDT','https://tutoringclub.com/fresnoca/student-intake-form/', 'https://tutoringclub.com/fresnoca/assessment-payment-form/','9423 North Fort Washington Road #106 Fresno, CA 93720',HOOK_CALI),
    (8,'Fountain Valley CA','PST/PDT','https://tutoringclub.com/fountain-valley-ca/student-intake-form/',None,'Our address is on 9985 Ellis Ave, Fountain Valley, CA 92708.',HOOK_CALI),
    (20,'Clovis','PST/PDT','https://tutoringclub.com/clovisca/student-intake-form/',None,'Our address is on 779 Herndon #105. We are on the northwest corner of Herndon and Clovis right next to the Starbucks.',HOOK_CALI),
    (87, 'Downey', 'PST/PDT','https://tutoringclub.com/downeyca/student-intake-form/',None,'8554 Firestone Blvd, Ste A Downey, CA 90241',HOOK_CALI)
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
                'webhook_link':franchise[6]
            }
    return {'assessment_link': None, 'payment_link': None, 'map_link': None, 'webhook_link': None}  # Default if not found

def generate_message(automation_stage, parent_name, student_names, greeting,
                     franchise_id, assessment_date, assessment_day,
                     assessment_date_pretty, assessment_time):
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
Hi {parent_name}! It’s Katie from Tutoring Club Clovis, just confirming your visit with us {relative_day}.

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
        message_template = (
            intro_message_one
            + assessment_link_message_one
            + payment_link_message_one
            + closing_message_one
        )
    elif automation_stage == "Assessment2":
        message_template = (
            intro_message_two
            + assessment_link_message_two
            + payment_link_message_two
            + map_link_message
            + closing_message_two
        )
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
    Sends text for the given row if it passes validation.
    Returns True if text was sent, otherwise False.
    """
    input_data = {
        "InquiryID": row['InquiryID'],
        "AutomationStage": row['AutomationStage'],
        "FranchiseID": row['FranchiseID'],
        "AssessmentDate": row['AssessmentDate'],
        "AssessmentTime": row['AssessmentTime'],
        "AssessmentEmail": row['AssessmentEmail'],
        "AssessmentPhone": row['AssessmentPhone'],
        "GuardianFirstName": row['GuardianFirstName'],
        "StudentString": row['StudentString']
    }
    # Validate
    try:
        validate_input(input_data)
    except ValueError as e:
        print(f"Skipping row due to validation error: {e}")
        return False

    # Format date/time and greeting
    assessment_date = parse(str(input_data['AssessmentDate']))
    assessment_day = assessment_date.strftime('%A')
    assessment_date_pretty = assessment_date.strftime('%B %d')
    assessment_time = parse(str(input_data['AssessmentTime'])).strftime('%I:%M %p')
    greeting = format_greeting(input_data['FranchiseID'])

    # Process StudentString for first names
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

    # Send to Zapier
    send_to_zapier(message, input_data, input_data['FranchiseID'])
    return True

###_____Main Function_____###
def main():
    # 1) Fetch the DataFrame from SQL Server
    print("Fetching data from SQL Server...")
    df_server = Assessment1DataCollectionsOnly.fetch_assessment_data(
        Assessment1DataCollectionsOnly.engine
    )

    # 2) Fetch the Cache from SQLite
    print("Fetching data from local SQLite cache...")
    df_cache = Assessment1SQLiteFunctions.select_assessment_cache(
        Assessment1SQLiteFunctions.engine
    )

    if df_server.empty and df_cache.empty:
        print("No data in server or cache. Nothing to do.")
        return

    # Convert sets of InquiryIDs for the usual new/extraneous logic
    server_ids = set(df_server['InquiryID'].unique())
    cache_ids = set(df_cache['InquiryID'].unique())

    # --- STEP A: Handle truly extraneous rows ---
    extraneous_ids = cache_ids - server_ids  # IDs in cache not in server
    if extraneous_ids:
        print(f"Deleting {len(extraneous_ids)} extraneous records from cache.")
        Assessment1SQLiteFunctions.delete_assessment_cache(
            Assessment1SQLiteFunctions.engine,
            extraneous_ids
        )

    # --- STEP B: Handle reschedules for matching IDs ---
    #  1) Find intersection of IDs in both server & cache
    intersect_ids = server_ids & cache_ids
    if intersect_ids:
        # 2) Subset both DataFrames to just the intersecting IDs
        df_server_intersect = df_server[df_server['InquiryID'].isin(intersect_ids)]
        df_cache_intersect = df_cache[df_cache['InquiryID'].isin(intersect_ids)]

        # 3) Convert date/time columns to consistent types (date, time, or datetime)
        #    so we can compare them reliably. We’ll do them as strings or datetime
        #    as you prefer. For demonstration, we’ll parse them to datetime.
        #    Adjust your column names if needed.
        def parse_datetime(df, date_col, time_col):
            """
            Returns a list of combined datetime objects or None if parsing fails.
            """
            combined = []
            for idx, row in df.iterrows():
                try:
                    # Convert date to date object
                    dt_date = pd.to_datetime(str(row[date_col])).date()
                    # Convert time to time object (or a datetime)
                    dt_time = pd.to_datetime(str(row[time_col])).time()
                    # Combine them into a single datetime
                    combined.append(datetime.datetime.combine(dt_date, dt_time))
                except Exception:
                    combined.append(None)
            return combined

        df_server_intersect = df_server_intersect.copy()
        df_cache_intersect = df_cache_intersect.copy()

        # Create a combined "AssessmentDatetime" in each
        df_server_intersect["AssessmentDatetime"] = parse_datetime(
            df_server_intersect, "AssessmentDate", "AssessmentTime"
        )
        df_cache_intersect["AssessmentDatetime"] = parse_datetime(
            df_cache_intersect, "AssessmentDate", "AssessmentTime"
        )

        # 4) Merge them on InquiryID to compare date/time
        merged = pd.merge(
            df_server_intersect[["InquiryID", "AssessmentDatetime"]],
            df_cache_intersect[["InquiryID", "AssessmentDatetime"]],
            on="InquiryID",
            suffixes=("_srv", "_cache")
        )

        # 5) Identify rows that differ in date/time
        #    If the date/time is different => "rescheduled"
        rescheduled_ids = []
        for idx, row in merged.iterrows():
            dt_server = row["AssessmentDatetime_srv"]
            dt_cache = row["AssessmentDatetime_cache"]
            # If different => treat as rescheduled
            if dt_server != dt_cache:
                rescheduled_ids.append(row["InquiryID"])

        # 6) Delete any rescheduled IDs from the cache so they can be re-inserted
        if rescheduled_ids:
            print(f"Found {len(rescheduled_ids)} reschedules. Deleting them from cache.")
            Assessment1SQLiteFunctions.delete_assessment_cache(
                Assessment1SQLiteFunctions.engine, 
                rescheduled_ids
            )

    # --- STEP C: Now that extraneous and rescheduled IDs have been removed,
    #             the server has "new" or "changed" IDs that aren't in cache.

    # Recalculate the cache to reflect those deletions
    df_cache_after_delete = Assessment1SQLiteFunctions.select_assessment_cache(
        Assessment1SQLiteFunctions.engine
    )
    cache_ids_after_delete = set(df_cache_after_delete["InquiryID"].unique())

    # 7) Insert new or rescheduled IDs
    new_ids = server_ids - cache_ids_after_delete
    if new_ids:
        df_new = df_server[df_server['InquiryID'].isin(new_ids)]
        print(f"Inserting {len(df_new)} new records into cache (including reschedules).")
        Assessment1SQLiteFunctions.insert_assessment_cache(
            Assessment1SQLiteFunctions.engine,
            df_new
        )

    # --- STEP D: Finally, re-fetch the cache to see all rows with IsText = 'No' for texting
    df_cache_current = Assessment1SQLiteFunctions.select_assessment_cache(
        Assessment1SQLiteFunctions.engine
    )
    df_to_text = df_cache_current[df_cache_current['IsText'] == 'No']

    if df_to_text.empty:
        print("No rows require texting (IsText = 'No').")
        return

    print(f"Sending texts for {len(df_to_text)} rows...")
    for idx, row in df_to_text.iterrows():
        # Attempt to send text
        text_sent = process_row(row)
        if text_sent:
            # Mark IsText = 'Yes'
            inquiry_id = row['InquiryID']
            Assessment1SQLiteFunctions.update_assessment_cache(
                Assessment1SQLiteFunctions.engine,
                [inquiry_id]
            )
        # Optional: short delay so we don't spam the system
        time.sleep(2)

if __name__ == "__main__":
    main()