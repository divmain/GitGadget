import os
from collections import namedtuple

from ..constants import MERGE_CONFLICT_PORCELAIN_STATUSES


MYPY = False
if MYPY:
    from GitSavvy.core.git_command import (
        HistoryMixin,
        _GitCommand,
    )

    class mixin_base(
        HistoryMixin,
        _GitCommand,
    ):
        pass

else:
    mixin_base = object

FileStatus = namedtuple("FileStatus", ("path", "path_alt", "index_status", "working_status"))

IndexedEntry = namedtuple("IndexEntry", (
    "src_path",
    "dst_path",
    "src_mode",
    "dst_mode",
    "src_hash",
    "dst_hash",
    "status",
    "status_score"
))
IndexedEntry.__new__.__defaults__ = (None, ) * 8


class StatusMixin(mixin_base):

    def _get_status(self):
        return self.git("status", "--porcelain", "-z", "-b",
                        custom_environ={"GIT_OPTIONAL_LOCKS": "0"}).rstrip("\x00").split("\x00")

    def _parse_status_for_file_statuses(self, lines):
        porcelain_entries = lines[1:].__iter__()
        entries = []

        for entry in porcelain_entries:
            if not entry:
                continue
            index_status = entry[0]
            working_status = entry[1].strip() or None
            path = entry[3:]
            path_alt = porcelain_entries.__next__() if index_status in ["R", "C"] else None
            entries.append(FileStatus(path, path_alt, index_status, working_status))

        return entries

    def get_status(self):
        """
        Return a list of FileStatus objects.  These objects correspond
        to all files that are 1) staged, 2) modified, 3) new, 4) deleted,
        5) renamed, or 6) copied as well as additional status information that can
        occur mid-merge.
        """

        lines = self._get_status()
        return self._parse_status_for_file_statuses(lines)

    def _get_indexed_entry(self, raw_entry):
        """
        Parse a diff-index entry into an IndexEntry object.  Each input entry
        will have either three NUL-separated fields if the file has been renamed,
        and two if it has not been renamed.

        The first field will always contain the meta_data related to the field,
        which includes: original and new file-system mode, the original and new
        git object-hashes, and a status letter indicating the nature of the
        change.
        """
        parts = [part for part in raw_entry.split("\x00") if part]
        if len(parts) == 2:
            meta_data, src_path = parts
            dst_path = src_path
        elif len(parts) == 3:
            meta_data, src_path, dst_path = parts

        src_mode, dst_mode, src_hash, dst_hash, status = meta_data

        status_score = status[1:]
        if status_score:
            status = status[0]

        return IndexedEntry(
            src_path,
            dst_path,
            src_mode,
            dst_mode,
            src_hash,
            dst_hash,
            status,
            status_score
        )

    def get_indexed(self):
        """
        Return a list of `IndexEntry`s.  Each entry in the list corresponds
        to a file that 1) is in HEAD, and 2) is staged with changes.
        """
        # Return an entry for each file with a difference between HEAD and its
        # counterpart in the current index.  Entries will be separated by `:` and
        # each field will be separated by NUL charachters.
        stdout = self.git("diff-index", "-z", "--cached", "HEAD")

        return [
            self._get_indexed_entry(raw_entry)
            for raw_entry in stdout.split(":")
            if raw_entry
        ]

    def sort_status_entries(self, file_status_list):
        """
        Take entries from `git status` and sort them into groups.
        """
        staged, unstaged, untracked, conflicts = [], [], [], []

        for f in file_status_list:
            if (f.index_status, f.working_status) in MERGE_CONFLICT_PORCELAIN_STATUSES:
                conflicts.append(f)
                continue
            if f.index_status == "?":
                untracked.append(f)
                continue
            elif f.working_status in ("M", "D", "T", "A"):
                unstaged.append(f)
            if f.index_status != " ":
                staged.append(f)

        return staged, unstaged, untracked, conflicts

    def in_rebase(self):
        return self.in_rebase_apply() or self.in_rebase_merge()

    def in_rebase_apply(self):
        return os.path.isdir(self._rebase_apply_dir)

    def in_rebase_merge(self):
        return os.path.isdir(self._rebase_merge_dir)

    @property
    def _rebase_apply_dir(self):
        return os.path.join(self.repo_path, ".git", "rebase-apply")

    @property
    def _rebase_merge_dir(self):
        return os.path.join(self.repo_path, ".git", "rebase-merge")

    @property
    def _rebase_dir(self):
        return self._rebase_merge_dir if self.in_rebase_merge() else self._rebase_apply_dir

    def rebase_branch_name(self):
        return self._read_rebase_file("head-name").replace("refs/heads/", "")

    def rebase_orig_head(self):
        # type: () -> str
        return self._read_rebase_file("orig-head")

    def rebase_conflict_at(self):
        # type: () -> str
        if self.in_rebase_merge():
            return (
                self._read_rebase_file("stopped-sha")
                or self._read_rebase_file("current-commit")
            )
        else:
            return self._read_rebase_file("original-commit")

    def rebase_onto_commit(self):
        # type: () -> str
        return self._read_rebase_file("onto")

    def _read_rebase_file(self, fname):
        # type: (str) -> str
        path = os.path.join(self._rebase_dir, fname)
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except Exception:
            return ""

    def in_merge(self):
        return os.path.exists(os.path.join(self.repo_path, ".git", "MERGE_HEAD"))

    def merge_head(self):
        path = os.path.join(self.repo_path, ".git", "MERGE_HEAD")
        with open(path, "r") as f:
            commit_hash = f.read().strip()
        return self.get_short_hash(commit_hash)
