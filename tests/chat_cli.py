"""
Console chat for testing the AI engine without the GUI.
Run from the project root with:   python -m tests.chat_cli
"""
from app.brain.ai_engine import AIEngine, AIEngineError


def main():
    engine = AIEngine()
    print("Checking Ollama...")
    kind, message = engine.check_connection()
    print(f"[{kind}] {message}")
    if kind != "ok":
        return

    print("Type a message. Commands: 'reset' clears memory, 'exit' quits.\n")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break
        if text.lower() == "reset":
            engine.reset()
            print("(memory cleared)\n")
            continue

        print("OPTIMUS: ", end="", flush=True)
        try:
            for piece in engine.stream_reply(text):
                print(piece, end="", flush=True)  # Words appear as they are generated
        except AIEngineError as err:
            print(f"\n[{err.kind}] {err.message}")
        print("\n")


if __name__ == "__main__":
    main()