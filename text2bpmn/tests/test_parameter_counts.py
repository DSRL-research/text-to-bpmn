"""Table 4's parameter counts: read from weights files without running them."""
import json
import pickle
import struct
import zipfile

import pytest

from text2bpmn.checks import parameter_counts as pc


def test_a_safetensors_header_gives_every_tensor_shape(tmp_path):
    header = {"a": {"dtype": "F32", "shape": [3, 4], "data_offsets": [0, 48]},
              "b": {"dtype": "F32", "shape": [5], "data_offsets": [48, 68]},
              "__metadata__": {"format": "pt"}}
    raw = json.dumps(header).encode()
    path = tmp_path / "model.safetensors"
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + bytes(68))
    assert pc.shapes(path) == {"a": (3, 4), "b": (5,)}
    assert pc.count(path)["parameters"] == 17


@pytest.fixture
def saved_model(tmp_path):
    torch = pytest.importorskip("torch")
    model = torch.nn.Sequential(torch.nn.Linear(7, 3), torch.nn.LayerNorm(3), torch.nn.Embedding(11, 3))
    path = tmp_path / "pytorch_model.bin"
    torch.save(model.state_dict(), path)
    return model, path


def test_the_tensor_sizes_of_a_torch_file_add_up_to_its_parameters(saved_model):
    model, path = saved_model
    assert pc.count(path)["parameters"] == sum(p.numel() for p in model.parameters())
    assert pc.count(path)["format"] == "pytorch zip"


class Boom:
    def __reduce__(self):
        return (print, ("this must not run",))


def test_a_pickle_naming_any_other_global_runs_nothing(tmp_path, capsys):
    path = tmp_path / "evil.bin"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("archive/data.pkl", pickle.dumps({"x": Boom()}, protocol=2))
    assert pc.torch_zip_shapes(path) == {}
    assert "must not run" not in capsys.readouterr().out


def test_the_record_lists_every_configuration_of_table_4_once():
    rows = [row for row, _, _ in pc.MODELS]
    assert len(rows) == len(set(rows)) == 7
