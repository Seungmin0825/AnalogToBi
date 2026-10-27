"""
GPT decoder with a learned absolute position embedding.

This is the architecture of the released checkpoint: token embeddings plus a
learned table of block_size position embeddings, added at the input, followed
by pre-norm Transformer blocks. Positions index the table directly, so a
sequence can be at most block_size tokens long; generation stops well before
that (max_length 1020 < block_size 1024), so no context window ever slides.
"""

import torch
import torch.nn as nn
from torch.nn import functional as F


class Head(nn.Module):
    """Causal self-attention head."""
    def __init__(self, head_size, n_embd, block_size, dropout):
        super().__init__()
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        # rebuilt on construction rather than saved: 36 copies of this constant
        # mask would be three quarters of the checkpoint
        self.register_buffer('tril', torch.tril(torch.ones(block_size, block_size)),
                             persistent=False)

        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        """Attend over the prefix of each position; x is (B, T, n_embd), the output (B, T, head_size)."""
        B,T,C = x.shape
        k = self.key(x)
        q = self.query(x)
        wei = q @ k.transpose(-2,-1) * k.shape[-1]**-0.5
        wei = wei.masked_fill(self.tril[:T, :T] == 0, float('-inf'))
        wei = F.softmax(wei, dim=-1)
        wei = self.dropout(wei)
        v = self.value(x)
        out = wei @ v
        return out


class MultiHeadAttention(nn.Module):
    """Parallel attention heads concatenated and projected back to n_embd."""
    def __init__(self, num_heads, head_size, n_embd, block_size, dropout):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size, n_embd, block_size, dropout)
                                    for _ in range(num_heads)])
        self.proj = nn.Linear(head_size * num_heads, n_embd)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        """Concatenate the heads and project back to n_embd."""
        out = torch.cat([h(x) for h in self.heads], dim=-1)
        out = self.dropout(self.proj(out))
        return out


class FeedForward(nn.Module):
    """Position-wise two-layer MLP with a 4x hidden expansion and ReLU."""
    def __init__(self, n_embd, dropout):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        """Apply the MLP position-wise."""
        return self.net(x)


class Block(nn.Module):
    """Pre-norm Transformer block: self-attention and feed-forward sublayers, each with a residual connection."""
    def __init__(self, n_embd, n_head, block_size, dropout):
        super().__init__()
        head_size = n_embd // n_head
        self.sa = MultiHeadAttention(n_head, head_size, n_embd, block_size, dropout)
        self.ffwd = FeedForward(n_embd, dropout)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x):
        """Residual self-attention followed by residual feed-forward."""
        x = x + self.sa(self.ln1(x))
        x = x + self.ffwd(self.ln2(x))
        return x


class GPTLanguageModel(nn.Module):
    """Decoder with learned absolute position embeddings; see the module docstring."""
    def __init__(self, vocab_size, n_embd, block_size, n_head, n_layer, dropout):
        super().__init__()
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        self.position_embedding_table = nn.Embedding(block_size, n_embd)
        self.blocks = nn.Sequential(*[Block(n_embd, n_head=n_head, block_size=block_size,
                                            dropout=dropout)
                                      for _ in range(n_layer)])
        self.ln_f = nn.LayerNorm(n_embd)
        self.lm_head = nn.Linear(n_embd, vocab_size)
        self.block_size = block_size
        self.apply(self._init_weights)

    def _init_weights(self, module):
        """Normal(0, 0.02) initialisation for linear and embedding weights; biases start at zero."""
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx, targets=None):
        """Return (logits, loss); the loss is None when no targets are given."""
        B, T = idx.shape
        if T > self.block_size:
            raise ValueError(f"sequence of {T} tokens exceeds the {self.block_size}-row "
                             f"position table")
        tok_emb = self.token_embedding_table(idx)
        pos_emb = self.position_embedding_table(torch.arange(T, device=idx.device))
        x = tok_emb + pos_emb
        x = self.blocks(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)

        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            # reshape rather than view: targets often arrive as a non-contiguous
            # slice of the batch tensor
            logits = logits.reshape(B*T, C)
            targets = targets.reshape(B*T)
            loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, idx, max_new_tokens, temperature=0.7):
        """Sample max_new_tokens tokens autoregressively at the given temperature, conditioning on the last block_size tokens."""
        for _ in range(max_new_tokens):
            idx_cond = idx[:, -self.block_size:]
            logits, loss = self(idx_cond)
            logits = logits[:, -1, :]
            logits = logits / temperature
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)

        return idx
