"""
main.py  –  Orchestrates the full pipeline:
  1. Fetch tasks from Quire API
  2. Process and enrich data
  3. Generate HTML + TXT reports
  4. Send email with attachments
"""
import smtplib
import os
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

import config
import quire_api
import data_processor
import report_generator


def send_email(subject: str, html_content: str, files_to_attach: list) -> None:
    """Send HTML email with optional file attachments via Gmail SMTP."""
    print("Sending email...")
    msg = MIMEMultipart()
    msg["From"]    = config.EMAIL_SENDER
    msg["To"]      = ", ".join(config.EMAIL_RECIPIENTS)
    msg["Subject"] = subject

    msg.attach(MIMEText(html_content, "html"))

    for file_path in files_to_attach:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_data = f.read()
            part = MIMEApplication(
                file_data.encode("utf-8"),
                Name=os.path.basename(file_path)
            )
            part["Content-Disposition"] = (
                f'attachment; filename="{os.path.basename(file_path)}"'
            )
            msg.attach(part)
            print(f"Attached: {file_path}")
        except Exception as e:
            print(f"Could not attach {file_path}: {e}")

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECIPIENTS, msg.as_string())
        server.quit()
        print("[SUCCESS] Email sent successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")


def main() -> None:
    # 1. Fetch raw data from Quire
    raw_data = quire_api.fetch_data()

    if not raw_data:
        print("No data found. Aborting.")
        return

    # 2. Process into clean DataFrame
    df = data_processor.get_processed_dataframe(raw_data)

    # 3. Generate HTML report + TXT attachment content
    html_report, txt_week_content, txt_month_content = report_generator.generate_reports(df)

    # 4. Write TXT attachments to disk
    file_week  = "Activity_Breakdown_Last_Week.txt"
    file_month = "Activity_Breakdown_Last_30_Days.txt"

    with open(file_week, "w", encoding="utf-8") as f:
        f.write(txt_week_content)

    with open(file_month, "w", encoding="utf-8") as f:
        f.write(txt_month_content)

    # 5. Send email
    subject = f"[Report] Project Status - {pd.Timestamp.now().strftime('%Y-%m-%d')}"
    send_email(subject, html_report, [file_week, file_month])


if __name__ == "__main__":
    main()
