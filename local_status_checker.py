import discord
import psutil
import os
import getpass
from datetime import datetime
import requests
import winreg
from collections import namedtuple
from discord.ext import commands, tasks

# Set environment variables for secrets
TOKEN = os.environ['External Saved Environment Variable Name For Bot Token']
WEBHOOK = os.environ['External Saved Environment Variable Name For Webhook URL']
CHANNEL_ID = os.environ['External Saved Environment Variable Name For Channel ID']
AGGREGATE_SOCKET = os.environ['External Saved Environment Variable Name For Aggregate Script Listener']

intents = discord.Intents.all()
intents.messages = True  # Enable the message content intent

# Initialize bot with intents
bot = commands.Bot(command_prefix='!', intents=intents)

# List to store RDP connections and their reservations
rdp_connections = {'workstation1': None, 'workstation2': None, 'workstation3': None, 'workstation4': None}

# Define a namedtuple to store workstation status
WorkstationStatus = namedtuple('WorkstationStatus', ['workstation', 'rdp_status', 'logged_in', 'username'])

# Function to check RDP connection status
def check_rdp_connections(workstation):
    rdp_connections = False
    for conn in psutil.net_connections():
        if conn.status == 'ESTABLISHED' and conn.laddr.port == 3389:  # RDP port
            rdp_connections = True
            break
    return rdp_connections

# Function to check if RDP is enabled
def check_rdp_enabled(workstation):
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Terminal Server", 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(reg_key, "fDenyTSConnections")
        winreg.CloseKey(reg_key)
        return value == 0  # RDP is enabled if the value is 0
    except FileNotFoundError:
        return False  # Return False if the registry key is not found

# Function to check if workstation is logged in
def is_logged_in(workstation):
    # Check if there is a user logged in to the console session
    session_name = os.environ.get('SESSIONNAME')
    if session_name == 'Console':
        return True
    else:
        return False

# Function to get workstation status
def get_workstation_status(workstation_name):
    rdp_status = check_rdp_connections(workstation_name)
    rdp_enabled = check_rdp_enabled(workstation_name)
    logged_in = is_logged_in(workstation_name)
    username = getpass.getuser()

    return WorkstationStatus(workstation_name, rdp_status, logged_in, username, rdp_enabled)

# Function to reserve an RDP connection
def reserve_connection(connection_name, user_id):
    rdp_connections[connection_name] = {'user_id': user_id, 'timestamp': datetime.now()}

# Function to release an RDP connection
def release_connection(connection_name):
    rdp_connections[connection_name] = None

# Function to send workstation status to the aggregator script
def send_to_aggregator(workstation_status):
    # Here you would implement code to send the workstation status to the aggregator script
    # You can use any method for inter-process communication, such as HTTP requests, sockets, or messaging queues
    # For simplicity, let's assume we're sending a POST request to a URL where the aggregator script is listening
    # Ensure the local firewall allows connections on this port and that the web server is listening to the right network card
    aggregator_url = AGGREGATE_SOCKET + '/update_status'
    data = {
        'workstation': workstation_status.workstation,
        'rdp_status': workstation_status.rdp_status,
        'rdp_enabled': workstation_status.rdp_enabled,
        'logged_in': workstation_status.logged_in,
        'username': workstation_status.username
    }
    response = requests.post(aggregator_url, json=data)
    if response.status_code == 200:
        print("Workstation status sent to aggregator successfully.")
    else:
        print("Failed to send workstation status to aggregator.")


# Function to send RDP status update to Discord channel
def send_status_update(workstation_name):
    print("Sending status update...")  # Add this line to confirm the function is called

    # Get the status of the workstation where the script is running
    workstation_status = get_workstation_status(workstation_name)

    # Send the workstation status to the other script for aggregation
    send_to_aggregator(workstation_status)


# Command to display available RDP connections
@bot.command()
async def connections(ctx):
    connections_list = '\n'.join([f'{name}: {"In Use" if status else "Available"}' for name, status in rdp_connections.items()])
    await ctx.send(f'Available RDP connections:\n{connections_list}')

# Command to select and mark an RDP connection as in use
@bot.command()
async def use(ctx, connection_name: str):
    if connection_name in rdp_connections:
        if rdp_connections[connection_name] is None:
            reserve_connection(connection_name, ctx.author.id)
            await ctx.send(f'{connection_name} is now in use by {ctx.author.display_name}.')
        else:
            await ctx.send(f'{connection_name} is already in use by {bot.get_user(rdp_connections[connection_name]["user_id"]).display_name}.')
    else:
        await ctx.send(f'Invalid RDP connection name.')

# Command to mark an RDP connection as available
@bot.command()
async def release(ctx, connection_name: str):
    if connection_name in rdp_connections:
        if rdp_connections[connection_name] is not None:
            release_connection(connection_name)
            await ctx.send(f'{connection_name} is now available.')
        else:
            await ctx.send(f'{connection_name} is already available.')
    else:
        await ctx.send(f'Invalid RDP connection name.')

# Command to extend an RDP reservation
@bot.command()
async def extend(ctx):
    for connection_name, reservation_info in rdp_connections.items():
        if reservation_info is not None and reservation_info['user_id'] == ctx.author.id:
            reservation_info['timestamp'] = datetime.now()
            await ctx.send(f'Your reservation for {connection_name} has been extended.')
            return
    await ctx.send('You do not have an active reservation to extend.')

# Command to explain how the bot works
@bot.command()
async def whoareyou(ctx):
    help = '''
    Use Availibot to check available RDP connections and reserve your workstation.
    This is a manual process right now, but there is a 3 hour auto-timeout for check-ins.

    Workstations To Choose From:
    {{bluestn1, bluestn2, purplestn1, purplestn2}}

    Commands:
    !connections                  -> list all RDP connections
    !use {{workstation_name}}     -> check into the workstation
    !release {{workstation_name}} -> checkout of the workstation)
    !extend                       -> reset the 3 hour timeout
    '''

    await ctx.send(help)

# Automatic release task
@tasks.loop(minutes=10)
async def automatic_release():
    now = datetime.now()
    for connection_name, reservation_info in rdp_connections.items():
        if reservation_info is not None:
            reservation_time = reservation_info['timestamp']
            if (now - reservation_time).total_seconds() >= 180 * 60:  # 3 hour timeout
                release_connection(connection_name)
                channel = await bot.fetch_channel(CHANNEL_ID)
                await channel.send(f'{connection_name} has been automatically released due to inactivity.')

# Start automatic release task
async def start_background_tasks():
    await bot.wait_until_ready()

    # Ensure to use an async function for background tasks
    async def background_task():
        await bot.wait_until_ready()
        automatic_release.start()

    bot.loop.create_task(background_task())

# Run the bot
bot.run(TOKEN)