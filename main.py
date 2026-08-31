import requests

# Use the exact same topic name you subscribed to in the mobile app
TOPIC = "Result_is_out"

url = f"https://ntfy.sh/{TOPIC}"
headers = {
    "Title": "GCUF Portal Bot",
    "Priority": "high",
    "Tags": "tada,mortar_board"
}
message = "Test successful! Your results alert bot is ready."

try:
    response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
    if response.status_code == 200:
        print("Success! Notification sent to your phone.")
    else:
        print(f"Server responded with status code: {response.status_code}")
except Exception as e:
    print(f"Error sending alert: {e}")