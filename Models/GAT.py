import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv, global_mean_pool, global_max_pool


class GATClassifier(nn.Module):
    def __init__(self, vocab_size, num_classes, embedding_dim=64, hidden_dim=128, num_heads=4, num_layers=3, dropout=0.3):
        """
        GAT-based circuit classifier
        
        Args:
            vocab_size: Size of token vocabulary (for both nodes and edges)
            num_classes: Number of circuit types to classify
            embedding_dim: Dimension of token embeddings
            hidden_dim: Hidden dimension size
            num_heads: Number of attention heads
            num_layers: Number of GAT layers
            dropout: Dropout rate
        """
        super(GATClassifier, self).__init__()
        
        self.num_layers = num_layers
        self.dropout = dropout
        
        # Embedding layers (token index → embedding vector)
        # Node embedding
        self.node_embedding = nn.Embedding(vocab_size, embedding_dim)
        # Edge type embedding
        self.edge_embedding = nn.Embedding(vocab_size, embedding_dim)
        
        # Edge feature transformation
        self.edge_encoder = nn.Linear(embedding_dim, hidden_dim * num_heads)
        
        # GAT layers
        self.convs = nn.ModuleList()
        
        # First layer (from embedding_dim)
        self.convs.append(GATConv(embedding_dim, hidden_dim, heads=num_heads, dropout=dropout, edge_dim=hidden_dim * num_heads))
        
        # Middle layers
        for _ in range(num_layers - 2):
            self.convs.append(GATConv(hidden_dim * num_heads, hidden_dim, heads=num_heads, dropout=dropout, edge_dim=hidden_dim * num_heads))
        
        # Last layer (single head for simplicity)
        self.convs.append(GATConv(hidden_dim * num_heads, hidden_dim, heads=1, concat=False, dropout=dropout, edge_dim=hidden_dim * num_heads))
        
        # Batch normalization layers
        self.batch_norms = nn.ModuleList()
        for _ in range(num_layers - 1):
            self.batch_norms.append(nn.BatchNorm1d(hidden_dim * num_heads))
        self.batch_norms.append(nn.BatchNorm1d(hidden_dim))
        
        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),  # *2 for concat of mean and max pool
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, num_classes)
        )
        
    def forward(self, x, edge_index, edge_attr, batch):
        """
        Forward pass
        
        Args:
            x: Node token indices [num_nodes] (integers)
            edge_index: Edge indices [2, num_edges]
            edge_attr: Edge type indices [num_edges] (integers)
            batch: Batch assignment vector [num_nodes]
            
        Returns:
            logits: Classification logits [batch_size, num_classes]
        """
        # Embed node token indices to vectors
        x = self.node_embedding(x)
        
        # Embed edge type indices to vectors
        edge_attr = self.edge_embedding(edge_attr)
        edge_attr = self.edge_encoder(edge_attr)
        
        # Apply GAT layers with edge features
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index, edge_attr=edge_attr)
            x = self.batch_norms[i](x)
            if i < self.num_layers - 1:
                x = F.elu(x)
                x = F.dropout(x, p=self.dropout, training=self.training)
        
        # Global pooling (combine mean and max pooling)
        x_mean = global_mean_pool(x, batch)
        x_max = global_max_pool(x, batch)
        x = torch.cat([x_mean, x_max], dim=1)
        
        # Classification
        logits = self.classifier(x)
        
        return logits
    
    def predict(self, x, edge_index, edge_attr, batch):
        """
        Predict circuit type
        
        Args:
            x: Node token indices [num_nodes]
            edge_index: Edge indices [2, num_edges]
            edge_attr: Edge type indices [num_edges]
            batch: Batch assignment vector [num_nodes]
            
        Returns:
            predictions: Predicted class indices
            probabilities: Class probabilities
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x, edge_index, edge_attr, batch)
            probabilities = F.softmax(logits, dim=1)
            predictions = torch.argmax(probabilities, dim=1)
        return predictions, probabilities
