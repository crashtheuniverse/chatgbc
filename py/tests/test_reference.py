"""Pins the fp32 port to llama2.c's own published output.

test_all.py in karpathy/llama2.c runs stories260K at temperature 0 for 200 steps
with no prompt and expects exactly this text. Matching it character for
character is what makes reference.py a trustworthy oracle for everything
downstream - without it, "the output looks like a plausible TinyStory" would be
the only evidence that the port is faithful.
"""

import reference as ref

LLAMA2C_EXPECTED = (
    "Once upon a time, there was a little girl named Lily. She loved to play "
    "outside in the park. One day, she saw a big, red ball. She wanted to play "
    "with it, but it was too high.\n"
    "Lily's mom said, \"Lily, let's go to the park.\" Lily was sad and didn't "
    "know what to do. She said, \"I want to play with your ball, but I can't "
    "find it.\"\n"
    "Lily was sad and didn't know what to do. She said, \"I'm sorry, Lily. I "
    "didn't know what to do.\"\n"
    "Lily didn't want to help her mom, so she"
)


def test_matches_llama2c_reference_output():
    model, tok = ref.Model(), ref.Tokenizer()
    out = "".join(t for _, t in ref.generate(model, tok, "", steps=200, seq_len=512))
    assert out == LLAMA2C_EXPECTED


def test_config_matches_checkpoint():
    c = ref.Model().cfg
    assert (c.dim, c.hidden_dim, c.n_layers) == (64, 172, 5)
    assert (c.n_heads, c.n_kv_heads, c.vocab_size) == (8, 4, 512)
    assert (c.head_size, c.kv_dim) == (8, 32)
