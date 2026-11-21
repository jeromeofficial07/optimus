"""
Phase 7 tests using a TEMPORARY database (your real data is never touched).
Run from the project root:   python -m tests.storage_cli
"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.agent.commands import CommandRouter
from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.path_guard import PathGuard
from app.agent.registry import ToolContext
from app.agent.timeparse import extract_time
from app.storage.repositories import Storage
from app.tools.builtin import build_default_registry
from app.tools.productivity import register_productivity_tools

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed += bool(condition)
    failed += not condition
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f"   -> {detail}" if detail else ""))


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        path = Path(folder) / "test.db"
        storage = Storage(path)

        print("--- conversations and messages ---")
        conversation = storage.conversations.create("Test chat")
        storage.messages.add(conversation, "user", "hello")
        storage.messages.add(conversation, "assistant", "hi there")
        roles = [m["role"] for m in storage.messages.for_conversation(conversation)]
        check("save and load messages in order", roles == ["user", "assistant"])

        storage.close()
        storage = Storage(path)  # Simulates closing and reopening the application
        check("data survives a restart", len(storage.conversations.list()) == 1)
        storage.conversations.delete(conversation)
        check("deleting a conversation removes its messages",
              storage.messages.for_conversation(conversation) == [])

        print("\n--- memory ---")
        storage.memory.remember("favorite color", "blue")
        storage.memory.remember("favorite color", "green")  # Same key replaces the value
        check("remember and replace", storage.memory.get("favorite color") == "green")
        for i in range(12):
            storage.memory.remember(f"filler {i}", f"unrelated thing {i}")
        storage.memory.remember("pet", "a dog called Rex")
        hits = [m["key"] for m in storage.memory.relevant("tell me about my pet", limit=5)]
        check("relevant memory retrieval ranks matches first", "pet" in hits, str(hits))

        print("\n--- reminders ---")
        storage.reminders.add("overdue one", datetime.now() - timedelta(minutes=1))
        storage.reminders.add("future one", datetime.now() + timedelta(hours=1))
        due = storage.reminders.due()
        check("only the overdue reminder is due", [r["text"] for r in due] == ["overdue one"])
        storage.reminders.mark_fired(due[0]["id"])
        check("fired reminders are not due again", storage.reminders.due() == [])

        print("\n--- time understanding ---")
        for phrase in ("in 10 minutes", "tomorrow at 9am", "at 6 pm", "on friday at 2:30pm", "in an hour"):
            when, _ = extract_time(f"remind me {phrase} to test")
            check(f"'{phrase}'", when is not None and when > datetime.now(), str(when))

        print("\n--- command router (permission prompts are denied) ---")
        executor = ToolExecutor(build_default_registry(), ToolContext(guard=PathGuard([])))
        register_productivity_tools(executor.registry, storage)
        router = CommandRouter(executor, storage)
        callbacks = ToolCallbacks(confirm=lambda request: False)
        expectations = [
            ("my name is Jerome", "Jerome"),
            ("remember that my favorite city is Chennai", "Chennai"),
            ("add task buy milk tomorrow at 9am", "Added the task"),
            ("show my tasks", "buy milk"),
            ("complete task 1", "Marked task 1"),
            ("remind me in 10 minutes to stretch", "Reminder set"),
            ("show my reminders", "stretch"),
            ("cancel reminder 2", "Cancelled"),
            ("forget about favorite city", "won't do that"),
            ("what do you remember about me", "Chennai"),
        ]
        for text, expected in expectations:
            reply = router.handle(text, callbacks)
            check(f"'{text}'", reply is not None and expected.lower() in reply.lower(), (reply or "None")[:70])
        check("declined 'forget' left the memory in place", storage.memory.get("favorite city") == "Chennai")
        check("a normal question is NOT a command", router.handle("tell me a joke", callbacks) is None)
        check("'remember when...?' is a question, not a command",
              router.handle("remember when we met?", callbacks) is None)
        storage.close()

        print("\n--- damaged database recovery ---")
        bad = Path(folder) / "bad.db"
        bad.write_text("this is definitely not a database")
        recovered = Storage(bad)
        check("damaged file moved aside and a new database created",
              recovered.db.recovered_from is not None and recovered.conversations.list() == [])
        recovered.close()

    print(f"\n{passed} passed, {failed} failed.")


if __name__ == "__main__":
    main()