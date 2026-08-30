"""Conversation loop: an LLM decides which storefront/browser action to take
next; browser_agent.py actually performs it in a real, visible browser. Every
money-moving step (add_to_cart, checkout, pay) is routed through the same
gating.py / safety_kernel.py used by the rest of CartMind.
"""
import json
import os
import sys
import tempfile
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import groq
from groq import Groq

from browser_agent import BrowserAgent

MODEL = "openai/gpt-oss-120b"
VOICE_TRIGGERS = {"voice", "v", "mic", "speak"}
RECORD_SECONDS = 5
SAMPLE_RATE = 16000


def record_and_transcribe():
    """Records a few seconds from the default mic and transcribes with Groq
    Whisper — the same model the browser UI (audio_server.py) uses."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY is not set in .env — voice input is unavailable. Type your request instead.")
        return None
    try:
        import sounddevice as sd
        from groq import Groq
    except ImportError as exc:
        print(f"Voice input needs sounddevice + groq installed: {exc}")
        return None

    try:
        default_input = sd.query_devices(kind="input")
    except Exception as exc:
        print(f"No microphone/input device found: {exc}")
        try:
            print("Available devices:")
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    print(f"  [{i}] {d['name']} (inputs: {d['max_input_channels']})")
        except Exception:
            pass
        return None

    print(f"Recording for {RECORD_SECONDS}s on '{default_input['name']}'... speak now.")
    try:
        audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
    except Exception as exc:
        print(f"Recording failed: {exc}")
        return None
    print("Recording done. Transcribing...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        wav_path = tmp.name

    try:
        client = Groq(api_key=api_key)
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=("command.wav", f.read()),
                model="whisper-large-v3-turbo",
                response_format="json",
                temperature=0,
            )
        return result.text.strip()
    except Exception as exc:
        print(f"Transcription failed: {exc}")
        return None
    finally:
        os.unlink(wav_path)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the storefront catalog by free-text query, and optionally narrow by color or max price. Call this again with a color to narrow an existing result set.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search, e.g. 'dress'. Leave empty when only narrowing by color."},
                    "color": {"type": "string", "description": "Optional color filter, e.g. 'black'."},
                    "max_price": {"type": "integer", "description": "Optional max price in INR."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "login",
            "description": "Log in with an email and password. If no account exists yet with that email, one is created automatically with the same credentials. Call this before checkout if checkout reports requires_login=true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "password": {"type": "string"},
                    "name": {"type": "string", "description": "Optional display name, used only if a new account is created."},
                },
                "required": ["email", "password"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_product",
            "description": "Open a specific product's page by SKU.",
            "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add the currently open product to the cart.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout",
            "description": "Go to checkout. This creates a real Razorpay TEST MODE order after the deterministic gating/safety checks pass, or returns a block reason if it fails a check.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pay_with_test_card",
            "description": "Open the real Razorpay Checkout modal and type a TEST MODE card into it live, then submit payment. Only call this after checkout() has succeeded and the user has explicitly confirmed they want to pay. Omit card_number/expiry/cvv to use the known-working default domestic test card — do not guess a generic card number like 4111111111111111, Razorpay's India TEST MODE rejects those.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_number": {"type": "string", "description": "Leave unset unless the user specifies a card."},
                    "expiry": {"type": "string", "description": "Leave unset unless the user specifies an expiry."},
                    "cvv": {"type": "string", "description": "Leave unset unless the user specifies a CVV."},
                },
            },
        },
    },
]

SYSTEM_PROMPT = """You are CartMind's shopping agent driving a real browser against a demo storefront.
Narrow the catalog conversationally (e.g. "dress" then "black") using search_catalog.
Never call add_to_cart, checkout, or pay_with_test_card without the user explicitly telling you to do so in this turn.
If checkout() reports blocked=true, explain the reason in plain language and stop — do not retry blindly or invent a workaround.
If checkout() reports requires_login=true, call login with the email/password the user gave you (or ask for them if they
haven't), then retry checkout automatically — no need to ask again once you have credentials.

When calling pay_with_test_card, unless the user gives you specific card details to use, ALWAYS default to:
  card_number: 5267318187975449
  expiry: 12/28
  cvv: 123
Do NOT use 4111111111111111 or any other generic/well-known test card — Razorpay's India TEST MODE
rejects those as "international card not supported" mid-entry, which looks like a typing bug but isn't.
Only the domestic test cards below are known to work here:
  5267318187975449 (Mastercard), 4012888888881881 (Visa), 5104060000000008 (Mastercard)

Keep replies short and concrete: what you found, what you're about to do, and why."""


DEFAULT_CARD = {"card_number": "5267318187975449", "expiry": "12/28", "cvv": "123"}
KNOWN_BAD_CARDS = {"4111111111111111", "4111 1111 1111 1111"}


def dispatch_tool(name, tool_input, browser: BrowserAgent):
    if name == "search_catalog":
        results = browser.search(query=tool_input.get("query", ""), color=tool_input.get("color"), max_price=tool_input.get("max_price"))
        return {"count": len(results), "products": results[:8]}

    if name == "login":
        return browser.login(tool_input["email"], tool_input["password"], tool_input.get("name", ""))

    if name == "select_product":
        browser.open_product(tool_input["sku"])
        return {"opened": tool_input["sku"]}

    if name == "add_to_cart":
        browser.add_to_cart()
        return {"added": True}

    if name == "checkout":
        return browser.go_to_checkout()

    if name == "pay_with_test_card":
        card_number = tool_input.get("card_number") or DEFAULT_CARD["card_number"]
        if card_number.replace(" ", "") in KNOWN_BAD_CARDS:
            card_number = DEFAULT_CARD["card_number"]
        expiry = tool_input.get("expiry") or DEFAULT_CARD["expiry"]
        cvv = tool_input.get("cvv") or DEFAULT_CARD["cvv"]
        return browser.pay_with_card(card_number, expiry, cvv)

    return {"error": f"Unknown tool {name}"}


def run():
    client = Groq()
    browser = BrowserAgent(headless=False)
    browser.page.goto(browser.base_url)
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("CartMind agent ready. A live browser window is open on the storefront — watch it there.")
    print("Type your request, type 'voice' to speak instead, or 'quit' to exit.")
    try:
        while True:
            raw = input("\nYou: ").strip()
            if raw.lower() in ("quit", "exit"):
                break

            if raw.lower() in VOICE_TRIGGERS:
                transcript = record_and_transcribe()
                if not transcript:
                    continue
                edited = input(f'Transcribed: "{transcript}"\nPress Enter to send as-is, or type a correction: ').strip()
                user_message = edited or transcript
            else:
                user_message = raw

            if not user_message:
                continue

            history.append({"role": "user", "content": user_message})

            while True:
                message = None
                for attempt in range(3):
                    try:
                        response = client.chat.completions.create(
                            model=MODEL,
                            max_tokens=1024,
                            tools=TOOLS,
                            tool_choice="auto",
                            messages=history,
                        )
                        message = response.choices[0].message
                        break
                    except groq.BadRequestError as exc:
                        # gpt-oss occasionally leaks its internal reasoning-channel
                        # tag into the tool name (e.g. "checkout<|channel|>commentary"),
                        # which the API then rejects. Retrying is usually enough.
                        print(f"  [warn] model returned a malformed tool call, retrying ({attempt + 1}/3): {exc}")
                if message is None:
                    print("Agent: Sorry, I hit a repeated error talking to the model. Try rephrasing your last message.")
                    break

                history.append(message.model_dump(exclude_unset=True, exclude_none=True))

                if message.content:
                    print("Agent:", message.content)

                if not message.tool_calls:
                    break

                for call in message.tool_calls:
                    tool_input = json.loads(call.function.arguments or "{}")
                    print(f"  [tool] {call.function.name}({json.dumps(tool_input)})")
                    try:
                        result = dispatch_tool(call.function.name, tool_input, browser)
                    except Exception as exc:
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                    print(f"  [result] {json.dumps(result)[:300]}")
                    history.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    })
    finally:
        browser.close()


if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        print("Set GROQ_API_KEY in .env before running the agent.")
        sys.exit(1)
    run()
