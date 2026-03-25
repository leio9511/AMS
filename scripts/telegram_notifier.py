import sys
import subprocess

def send_telegram_message(message):
    """Sends a message to the main Telegram chat via OpenClaw CLI."""
    # The main session key is agent:main:main
    try:
        subprocess.run(
            ["openclaw", "message", "send", "--target", "agent:main:main", "--message", message],
            check=True, capture_output=True
        )
        print("[*] Telegram notification sent.")
    except Exception as e:
        print(f"[!] Failed to send Telegram notification: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_telegram_message(sys.argv[1])
