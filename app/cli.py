#!/usr/bin/env python3
"""CLI/REPL interface for the AI Agent - Stage 12.

Provides an interactive command-line interface with:
- Chat loop with history
- Slash commands (/help, /tools, /memory, /clear, /exit, /mode)
- Colored output
- Session persistence
"""

import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.agent import Agent
from app.core.permissions import ApprovalMode


class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    GRAY = '\033[90m'


def colorize(text: str, color: str) -> str:
    """Wrap text with ANSI color codes."""
    return f"{color}{text}{Colors.RESET}"


def print_banner():
    """Print the CLI banner."""
    print(colorize("╔═══════════════════════════════════════════════════════════════╗", Colors.CYAN))
    print(colorize("║                    AI Agent CLI - Stage 12                    ║", Colors.CYAN))
    print(colorize("║              Interactive REPL with Tool Support               ║", Colors.CYAN))
    print(colorize("╚═══════════════════════════════════════════════════════════════╝", Colors.CYAN))
    print()


def print_help():
    """Print help message with available commands."""
    print(colorize("\nAvailable Commands:", Colors.BOLD))
    print(f"  {colorize('/help', Colors.GREEN)}          - Show this help message")
    print(f"  {colorize('/tools', Colors.GREEN)}         - List available tools")
    print(f"  {colorize('/memory', Colors.GREEN)}        - Show conversation history")
    print(f"  {colorize('/clear', Colors.GREEN)}         - Clear conversation memory")
    print(f"  {colorize('/mode', Colors.GREEN)}          - Show/change approval mode")
    print(f"  {colorize('/save <file>', Colors.GREEN)}    - Save session to JSON file")
    print(f"  {colorize('/load <file>', Colors.GREEN)}    - Load session from JSON file")
    print(f"  {colorize('/exit', Colors.GREEN)}          - Exit the REPL (Ctrl+D also works)")
    print(f"  {colorize('/quit', Colors.GREEN)}          - Same as /exit")
    print()
    print(colorize("Usage:", Colors.BOLD))
    print("  Type your message and press Enter to chat with the agent.")
    print("  Slash commands start with '/' and are processed locally.")
    print()


def print_tools(agent: Agent):
    """Print available tools."""
    tools = agent.list_tools()
    print(colorize("\nAvailable Tools:", Colors.BOLD))
    for tool in tools:
        name = tool.get('name', 'unknown')
        desc = tool.get('description', 'No description')
        print(f"  {colorize(name, Colors.CYAN):20} - {desc}")
    print()


def print_memory(agent: Agent):
    """Print conversation memory."""
    messages = agent.get_memory()
    if not messages:
        print(colorize("  (empty)", Colors.GRAY))
        return

    print(colorize("\nConversation History:", Colors.BOLD))
    for i, msg in enumerate(messages):
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        # Truncate long messages
        if len(content) > 100:
            content = content[:97] + "..."

        if role == 'user':
            prefix = colorize("▸ User:", Colors.BLUE)
        elif role == 'assistant':
            prefix = colorize("▸ Agent:", Colors.GREEN)
        elif role == 'tool':
            prefix = colorize("▸ Tool:", Colors.YELLOW)
        else:
            prefix = f"▸ {role.capitalize()}:"

        print(f"  {prefix} {content}")
    print()


def print_mode(agent: Agent):
    """Print current approval mode."""
    mode = agent.permission_manager.approval_mode
    print(colorize(f"\nCurrent approval mode: {mode.name}", Colors.BOLD))
    print(colorize("Available modes:", Colors.DIM))
    for m in ApprovalMode:
        marker = colorize("→", Colors.GREEN) if m == mode else "  "
        print(f"  {marker} {m.name}")
    print()


def change_mode(agent: Agent, mode_name: str) -> bool:
    """Change approval mode."""
    try:
        new_mode = ApprovalMode[mode_name.upper()]
        agent.permission_manager.approval_mode = new_mode
        print(colorize(f"✓ Approval mode changed to {new_mode.name}", Colors.GREEN))
        return True
    except KeyError:
        print(colorize(f"✗ Unknown mode: {mode_name}", Colors.RED))
        print(colorize("Available modes: " + ", ".join(m.name for m in ApprovalMode), Colors.YELLOW))
        return False


def save_session(agent: Agent, filepath: str) -> bool:
    """Save session to JSON file."""
    try:
        data = {
            "messages": agent.get_memory(),
            "approval_mode": agent.permission_manager.approval_mode.name,
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        print(colorize(f"✓ Session saved to {filepath}", Colors.GREEN))
        return True
    except Exception as e:
        print(colorize(f"✗ Failed to save session: {e}", Colors.RED))
        return False


def load_session(agent: Agent, filepath: str) -> bool:
    """Load session from JSON file."""
    try:
        with open(filepath) as f:
            data = json.load(f)

        agent.clear_memory()
        for msg in data.get("messages", []):
            if msg.get('role') == 'user':
                agent.memory.add_user_message(msg['content'])
            elif msg.get('role') == 'assistant':
                agent.memory.add_agent_message(msg['content'])
            elif msg.get('role') == 'tool':
                # Tool observations are stored separately
                pass

        if "approval_mode" in data:
            change_mode(agent, data["approval_mode"])

        print(colorize(f"✓ Session loaded from {filepath}", Colors.GREEN))
        return True
    except Exception as e:
        print(colorize(f"✗ Failed to load session: {e}", Colors.RED))
        return False


def process_slash_command(agent: Agent, command: str) -> bool:
    """Process a slash command. Returns True if command was handled."""
    parts = command[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ('help', 'h', '?'):
        print_help()
        return True

    elif cmd == 'tools':
        print_tools(agent)
        return True

    elif cmd == 'memory':
        print_memory(agent)
        return True

    elif cmd == 'clear':
        agent.clear_memory()
        print(colorize("✓ Conversation memory cleared", Colors.GREEN))
        return True

    elif cmd == 'mode':
        if arg:
            change_mode(agent, arg)
        else:
            print_mode(agent)
        return True

    elif cmd == 'save':
        if not arg:
            print(colorize("✗ Usage: /save <filepath>", Colors.RED))
            return True
        save_session(agent, arg)
        return True

    elif cmd == 'load':
        if not arg:
            print(colorize("✗ Usage: /load <filepath>", Colors.RED))
            return True
        load_session(agent, arg)
        return True

    elif cmd in ('exit', 'quit', 'q'):
        print(colorize("\nGoodbye!", Colors.CYAN))
        sys.exit(0)

    else:
        print(colorize(f"✗ Unknown command: /{cmd}", Colors.RED))
        print(colorize("Type /help for available commands", Colors.YELLOW))
        return True


def run_repl(agent: Agent):
    """Run the interactive REPL loop."""
    print_banner()
    print_help()
    print(colorize("Ready. Type your message or /help for commands.\n", Colors.GREEN))

    while True:
        try:
            # Get user input with colored prompt
            user_input = input(colorize("▸ ", Colors.BLUE)).strip()

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith('/'):
                process_slash_command(agent, user_input)
                continue

            # Process regular message
            print()
            try:
                response = agent.run(user_input)
                print(colorize(response, Colors.GREEN))
            except Exception as e:
                print(colorize(f"Error: {e}", Colors.RED))
            print()

        except KeyboardInterrupt:
            print(colorize("\n\nInterrupted. Type /exit to quit.", Colors.YELLOW))
            continue
        except EOFError:
            print(colorize("\n\nGoodbye!", Colors.CYAN))
            break


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="AI Agent CLI - Interactive REPL Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.cli                    # Start interactive REPL
  python -m app.cli --mode FULL_AUTO   # Start with FULL_AUTO approval mode
  python -m app.cli --message "Hello"  # Single message mode (non-interactive)
        """
    )
    parser.add_argument(
        '--mode',
        choices=[m.name for m in ApprovalMode],
        default='BALANCED',
        help='Initial approval mode (default: BALANCED)'
    )
    parser.add_argument(
        '--message', '-m',
        help='Single message mode - process one message and exit'
    )
    parser.add_argument(
        '--load',
        help='Load session from JSON file on startup'
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )

    args = parser.parse_args()

    # Disable colors if requested
    if args.no_color:
        Colors.RESET = Colors.BOLD = Colors.DIM = ''
        Colors.RED = Colors.GREEN = Colors.YELLOW = Colors.BLUE = ''
        Colors.MAGENTA = Colors.CYAN = Colors.GRAY = ''

    # Create agent
    agent = Agent()

    # Set approval mode
    try:
        agent.permission_manager.approval_mode = ApprovalMode[args.mode]
    except KeyError:
        print(colorize(f"Warning: Unknown mode {args.mode}, using BALANCED", Colors.YELLOW))

    # Load session if requested
    if args.load:
        load_session(agent, args.load)

    # Single message mode
    if args.message:
        try:
            response = agent.run(args.message)
            print(response)
        except Exception as e:
            print(colorize(f"Error: {e}", Colors.RED), file=sys.stderr)
            sys.exit(1)
        return

    # Interactive mode
    run_repl(agent)


if __name__ == '__main__':
    main()
