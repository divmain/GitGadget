from sublime_plugin import WindowCommand

from ..git_command import GitCommand


__all__ = (
    "gs_amend",
    "gs_quick_stage_current_file_and_amend",
)


class gs_amend(WindowCommand, GitCommand):
    def run(self):
        self.window.run_command("gs_commit", {"amend": True})


class gs_quick_stage_current_file_and_amend(gs_amend, GitCommand):
    def run(self):
        self.git("add", "--", self.file_path)
        self.window.status_message("staged {}".format(self.get_rel_path(self.file_path)))
        super().run()
