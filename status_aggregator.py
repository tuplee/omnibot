import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Discord webhook URL
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL Environment Variable')

# Endpoint to receive status updates from workstation scripts
@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json  # Extract status update from request body
    # Process status update (e.g., aggregate data, update database)
    workstation = data.get('workstation')
    rdp_status = data.get('rdp_status')
    logged_in = data.get('logged_in')
    username = data.get('username')
    print(f"Received status update from workstation {workstation}: RDP Status: {rdp_status}, Logged In: {logged_in}, Username: {username}")

    # Send status update to Discord server using webhook
    send_to_discord(workstation, rdp_status, logged_in, username)
    
    return jsonify({'message': 'Status update received successfully'})

# Function to send status update to Discord server using webhook
def send_to_discord(workstation, rdp_status, logged_in, username):
    data = {
        'content': f'**Workstation Status Update:**\nWorkstation: {workstation}\nRDP Status: {rdp_status}\nLogged In: {logged_in}\nUsername: {username}'
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data, headers=headers)
    if response.status_code == 200:
        print('Status update sent to Discord successfully.')
    else:
        print(f'Failed to send status update to Discord. Status code: {response.status_code}')

if __name__ == '__main__':
    app.run(host='NIC_IP_GOES_HERE', port=8000, debug=True)

