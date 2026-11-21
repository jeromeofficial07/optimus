"""
Memory, task and reminder tools. They are registered in the same registry as every
other tool, so they get validation, permission prompts and the audit log.

They are hidden from the AI model (HIDDEN_FROM_MODEL): the command router calls them, which
keeps the model's tool list short and reliable.
"""
from datetime import datetime

from app.agent.registry import HIDDEN_FROM_MODEL, Param, Risk, Tool, ToolError
from app.agent.timeparse import describe, extract_time, from_text
from app.storage.database import DatabaseError
from app.storage.repositories import Storage


def register_productivity_tools(registry, storage: Storage):
    def db_guard(function):
        """Turn a DatabaseError into a normal tool failure with a readable message."""
        def wrapper(ctx, **kwargs):
            try:
                return function(**kwargs)
            except DatabaseError as exc:
                raise ToolError(str(exc)) from exc
        return wrapper

    plural = lambda n, word: f"{n} {word}{'s' if n != 1 else ''}"

    # ---------------------------------------------------------------- memory
    @db_guard
    def remember_fact(key, value, category="general"):
        storage.memory.remember(key, value, category)
        return f"Remembered: {key.strip()} = {value.strip()}"

    @db_guard
    def forget_fact(key):
        if not storage.memory.forget(key):
            raise ToolError(f"I don't have anything stored under '{key}'.")
        return f"Forgot: {key.strip()}"

    @db_guard
    def list_memories():
        memories = storage.memory.all()
        if not memories:
            return "I haven't been asked to remember anything yet."
        return "\n".join([f"I remember {plural(len(memories), 'thing')}:"]
                         + [f"- {m['key']}: {m['value']}" for m in memories])

    # ---------------------------------------------------------------- tasks
    def task_by_number(number):
        tasks = storage.tasks.open_tasks()
        if not 1 <= number <= len(tasks):
            raise ToolError(f"There is no open task number {number}.")
        return tasks[number - 1]

    @db_guard
    def add_task(title, due=None):
        due_at = None
        if due:
            due_at, _ = extract_time(due)
            if due_at is None:
                raise ToolError("I couldn't understand that due date.")
        storage.tasks.add(title.strip(), due_at)
        return f"Added the task: {title.strip()}" + (f" (due {describe(due_at)})" if due_at else "") + "."

    @db_guard
    def list_tasks():
        tasks = storage.tasks.open_tasks()
        if not tasks:
            return "You have no open tasks."
        lines = [f"You have {plural(len(tasks), 'open task')}:"]
        for i, task in enumerate(tasks, 1):
            due = f" (due {describe(from_text(task['due_at']))})" if task["due_at"] else ""
            lines.append(f"{i}. {task['title']}{due}")
        return "\n".join(lines)

    @db_guard
    def complete_task(number):
        task = task_by_number(number)
        storage.tasks.complete(task["id"])
        return f"Marked task {number} done: {task['title']}."

    @db_guard
    def delete_task(number):
        task = task_by_number(number)
        storage.tasks.delete(task["id"])
        return f"Deleted task {number}: {task['title']}."

    # ---------------------------------------------------------------- reminders
    def reminder_by_number(number):
        reminders = storage.reminders.pending()
        if not 1 <= number <= len(reminders):
            raise ToolError(f"There is no pending reminder number {number}.")
        return reminders[number - 1]

    @db_guard
    def add_reminder(text, when):
        moment, _ = extract_time(when)
        if moment is None:
            raise ToolError("I couldn't understand that time. Try 'in 10 minutes' or 'tomorrow at 9am'.")
        if moment <= datetime.now():
            raise ToolError("That time has already passed.")
        storage.reminders.add(text.strip(), moment)
        return f"Reminder set for {describe(moment)}: {text.strip()}"

    @db_guard
    def list_reminders():
        reminders = storage.reminders.pending()
        if not reminders:
            return "You have no pending reminders."
        lines = [f"You have {plural(len(reminders), 'pending reminder')}:"]
        for i, item in enumerate(reminders, 1):
            lines.append(f"{i}. {item['text']} ({describe(from_text(item['remind_at']))})")
        return "\n".join(lines)

    @db_guard
    def cancel_reminder(number):
        reminder = reminder_by_number(number)
        storage.reminders.cancel(reminder["id"])
        return f"Cancelled the reminder: {reminder['text']}."

    # ---------------------------------------------------------------- registration
    number = lambda what: Param("number", "integer", f"The {what} number from the list", minimum=1, maximum=500)
    tools = [
        Tool("remember_fact", "Remember a fact or preference about the user.", remember_fact,
             (Param("key", "string", "Short label", max_length=80),
              Param("value", "string", "The fact", max_length=300),
              Param("category", "string", "Category", required=False, max_length=30)),
             status_text="Saving to memory..."),
        Tool("forget_fact", "Forget a remembered fact.", forget_fact,
             (Param("key", "string", "Label of the fact", max_length=80),),
             risk=Risk.DESTRUCTIVE, status_text="Forgetting...",
             confirm_text="Forget what I know about '{key}'?"),
        Tool("list_memories", "List remembered facts.", list_memories, status_text="Reading memory..."),
        Tool("add_task", "Add a task to the to-do list.", add_task,
             (Param("title", "string", "The task", max_length=200),
              Param("due", "string", "Optional due date and time", required=False, max_length=100)),
             status_text="Adding the task..."),
        Tool("list_tasks", "List open tasks.", list_tasks, status_text="Reading your tasks..."),
        Tool("complete_task", "Mark a task as done.", complete_task, (number("task"),),
             status_text="Completing the task..."),
        Tool("delete_task", "Delete a task.", delete_task, (number("task"),),
             risk=Risk.DESTRUCTIVE, status_text="Deleting the task...",
             confirm_text="Delete task {number}? This cannot be undone."),
        Tool("add_reminder", "Set a reminder.", add_reminder,
             (Param("text", "string", "What to remind about", max_length=300),
              Param("when", "string", "When to remind", max_length=100)),
             status_text="Setting the reminder..."),
        Tool("list_reminders", "List pending reminders.", list_reminders,
             status_text="Reading your reminders..."),
        Tool("cancel_reminder", "Cancel a reminder.", cancel_reminder, (number("reminder"),),
             status_text="Cancelling the reminder..."),
    ]
    for tool in tools:
        registry.register(tool)
        HIDDEN_FROM_MODEL.add(tool.name)