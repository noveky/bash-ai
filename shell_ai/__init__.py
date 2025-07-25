import argparse
import html
import os
import re
import sys

from .completion import request_completion
from .config import MAX_CONTEXT_LENGTH
from .models import Event, EventType, Ref
from .prompts import construct_prompt
from .utils import ask_yes_no, escape_printf, indent, print_styled, strip_ansi, styled

PRIMARY_COLOR = (38, 2, 255, 99, 132)
SECONDARY_COLOR = (38, 2, 255, 159, 64)


agent_name = None


def agent_display_name():
    return agent_name or "AI"


def flush_buffer(buffer: Ref[str], acc: Ref[str], event_queue: list[Event]):
    """Print the buffer contents to stderr and clear it."""

    if buffer.value:
        print_styled(buffer.value, end="", flush=True, file=sys.stderr)
        acc.value += buffer.value
        buffer.value = ""


def buffer_handler(buffer: Ref[str], acc: Ref[str], event_queue: list[Event]):
    """Handle the response stream buffer."""

    OPENING_TAG = "<suggest-command>"
    CLOSING_TAG = "</suggest-command>"

    # Check if the buffer contains tags or partial tags
    if buffer.value.find(OPENING_TAG) != -1 or any(
        buffer.value.endswith(OPENING_TAG[: j + 1]) for j in range(len(OPENING_TAG))
    ):
        # Replace tags and trigger event
        while True:
            changed = False

            if run_command_match := re.search(
                rf"{OPENING_TAG}(.*?){CLOSING_TAG}", buffer.value, re.DOTALL
            ):
                # Trigger command suggestion
                command = html.unescape(
                    run_command_match.group(1)
                )  # Unescape &lt;, &gt;, etc.
                buffer.value = (
                    buffer.value[: run_command_match.start()]
                    + styled(command, "bold", code_tuple=SECONDARY_COLOR)
                    + buffer.value[run_command_match.end() :]
                )
                event_queue.append(Event(EventType.SUGGEST_COMMAND, command))
                changed = True

            if not changed:
                break
    else:
        flush_buffer(buffer, acc, event_queue)


def start_handler(buffer: Ref[str], acc: Ref[str], event_queue: list[Event]):
    print_styled(
        f"{agent_display_name()}:", "bold", code_tuple=PRIMARY_COLOR, file=sys.stderr
    )


def stop_handler(buffer: Ref[str], acc: Ref[str], event_queue: list[Event]):
    flush_buffer(buffer, acc, event_queue)

    if not acc.value.endswith("\n"):
        # Print a final newline
        print(file=sys.stderr)


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="shell-ai", formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--agent-name", type=str, help="Agent name for the AI")
    parser.add_argument("--context-file", type=str, help="Path to the context file")
    parser.add_argument("--message", type=str, help="Message to the AI")

    args = parser.parse_args()

    return (
        str(args.agent_name),
        str(args.context_file) if args.context_file is not None else None,
        args.message,
    )


async def main():
    global agent_name
    agent_name, context_file, message = parse_arguments()

    # Read the shell session context if context file is provided
    session_context = None
    if context_file:
        try:
            with open(context_file, "r", errors="replace") as f:
                session_context = strip_ansi(f.read())
        except:
            pass

    # Construct the prompt
    prompt = construct_prompt(
        agent_name=agent_display_name(),
        is_top_level_agent=not agent_name,
        session_context=session_context[-(MAX_CONTEXT_LENGTH or 0) :]
        if session_context is not None
        else "Failed to acquire context",
        message=message,
    )

    # Invoke the LLM API and handle the response
    event_queue: list[Event] = []
    try:
        await request_completion(
            [{"role": "user", "content": prompt}],
            event_queue=event_queue,
            buffer_handler=buffer_handler,
            start_handler=start_handler,
            stop_handler=stop_handler,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Process the events from the response
    commands_to_run: list[str] = []
    for event in event_queue:
        if event.type == EventType.SUGGEST_COMMAND:
            # Ask the user for confirmation before running the command
            print(
                styled(
                    f"\n{agent_display_name()} suggests running this command:",
                    "bold",
                    code_tuple=PRIMARY_COLOR,
                ),
                file=sys.stderr,
            )
            print_styled(
                indent(event.data, 0),
                "bold",
                code_tuple=SECONDARY_COLOR,
                file=sys.stderr,
            )
            if ask_yes_no(styled("Approve?", "bold", code_tuple=PRIMARY_COLOR)):
                commands_to_run.append(event.data)

    # Construct the combined command
    combined_command = ""
    proceed_pattern = re.compile(r"ai proceed|ai \"proceed\"|ai \'proceed\'")
    has_proceed = False
    for i, command in enumerate(commands_to_run, 1):
        if proceed_pattern.search(command):
            has_proceed = True
        command = proceed_pattern.sub(
            f"ai-agent {agent_display_name()} proceed {message}", command
        )
        combined_command += f"printf {escape_printf(styled(f'\n{agent_display_name()} is executing approved command ({i}/{len(commands_to_run)}):', 'bold', code_tuple=PRIMARY_COLOR))};\n"
        combined_command += f"printf {escape_printf('\n')};\n"
        # combined_command += f"printf {escape_printf('\n' + indent(command, 0))};\n"
        combined_command += f"{{\n{command.strip()}\n}};"
    if commands_to_run and not has_proceed:
        combined_command += f"printf {escape_printf(styled(f'\n{agent_display_name()} done.\n', 'bold', code_tuple=PRIMARY_COLOR))};\n"

    # Write the combined command to stdout, which will be executed in shell using `eval`
    print(combined_command, file=sys.stdout)


def cleanup():
    pass
