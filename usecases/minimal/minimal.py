import pathlib
from dataclasses import dataclass, field

from mako.template import Template
from rich.panel import Panel

from capabilities import SSHRunCommand, SSHTestCredential
from utils import SSHConnection, llm_util
from usecases.base import use_case
from usecases.agents import Agent
from utils.cli_history import SlidingCliHistory

template_dir = pathlib.Path(__file__).parent
template_next_cmd = Template(filename=str(template_dir / "next_cmd.txt"))

@use_case("minimal_linux_privesc", "Showcase Minimal Linux Priv-Escalation")
@dataclass
class MinimalLinuxPrivesc(Agent):

    conn: SSHConnection = None
    
    _sliding_history: SlidingCliHistory = None

    def init(self):
        super().init()
        self._sliding_history = SlidingCliHistory(self.llm)
        self.add_capability(SSHRunCommand(conn=self.conn), default=True)
        self.add_capability(SSHTestCredential(conn=self.conn))
        self._template_size = self.llm.count_tokens(template_next_cmd.source)

    def perform_round(self, turn):
        got_root : bool = False

        with self.console.status("[bold green]Asking LLM for a new command..."):
            # get as much history as fits into the target context size
            history = self._sliding_history.get_history(self.llm.context_size - llm_util.SAFETY_MARGIN - self._template_size)

            # get the next command from the LLM
            answer = self.llm.get_response(template_next_cmd, capabilities=self.get_capability_block(), history=history, conn=self.conn)
            cmd = llm_util.cmd_output_fixer(answer.result)

        with self.console.status("[bold green]Executing that command..."):
                self.console.print(Panel(answer.result, title="[bold cyan]Got command from LLM:"))
                result, got_root = self.get_capability(cmd.split(" ", 1)[0])(cmd)

        # log and output the command and its result
        self.log_db.add_log_query(self._run_id, turn, cmd, result, answer)
        self._sliding_history.add_command(cmd, result)
        self.console.print(Panel(result, title=f"[bold cyan]{cmd}"))

        # if we got root, we can stop the loop
        return got_root