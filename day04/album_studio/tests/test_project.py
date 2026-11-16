"""Saving the user's choices safely (studio/project.py)."""
import json

from studio.project import Project


def project_at(path):
    """A Project whose choices are saved at path (without a photo folder around it)."""
    project = Project.__new__(Project)
    project.state_file = path
    project.state = project.load_state()
    return project


def test_choices_are_saved_and_read_back(tmp_path):
    project = project_at(tmp_path / "project.json")
    project.step_state("pick")["picked"] = ["a.jpg"]
    project.save()
    assert project_at(tmp_path / "project.json").state == {"steps": {"pick": {"picked": ["a.jpg"]}}}


def test_a_new_project_starts_empty(tmp_path):
    project = project_at(tmp_path / "project.json")
    assert project.state == {"steps": {}}
    assert project.step_state("group") == {} and "group" in project.state["steps"]


def test_each_save_keeps_the_previous_version_and_no_temporary_file(tmp_path):
    path = tmp_path / "project.json"
    project = project_at(path)
    project.step_state("pick")["target"] = 10
    project.save()
    project.step_state("pick")["target"] = 20
    project.save()
    assert json.loads(path.read_text())["steps"]["pick"]["target"] == 20
    assert json.loads((tmp_path / "project.json.bak").read_text())["steps"]["pick"]["target"] == 10
    assert not (tmp_path / "project.json.tmp").exists()


def test_a_damaged_file_falls_back_to_the_backup(tmp_path):
    (tmp_path / "project.json").write_text('{"steps": {"pick": {"picked": ["a.jp')  # cut off mid-save
    (tmp_path / "project.json.bak").write_text('{"steps": {"pick": {"picked": []}}}')
    assert project_at(tmp_path / "project.json").state == {"steps": {"pick": {"picked": []}}}


def test_damaged_and_no_backup_starts_empty_instead_of_crashing(tmp_path):
    (tmp_path / "project.json").write_text("not json")
    assert project_at(tmp_path / "project.json").state == {"steps": {}}
