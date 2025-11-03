#!/usr/bin/env python3
import numpy as np
import time

# Test data loading speed comparison
print("Testing data loading speeds...")

# 원래 방식 (Pretrain.py 스타일)
print("\n=== Original Pretrain.py style ===")
start_time = time.time()

# Load training data
train_data = np.load('Training.npy', allow_pickle=True)
print(f"Training data loaded. Shape: {train_data.shape}, dtype: {train_data.dtype}")

# Check data structure
if train_data.dtype == object:
    sample_lengths = []
    for i in range(min(10, len(train_data))):
        sample_lengths.append(len(train_data[i]))
    print(f"Sample sequence lengths: {sample_lengths}")

loading_time = time.time() - start_time
print(f"Original loading time: {loading_time:.2f} seconds")

# 멀티GPU 방식 테스트 (for loop 방식)
print("\n=== MultiGPU style (for loop) ===")
start_time = time.time()

# Simulate the multi-GPU data processing
devices = ['NM1', 'NM1_D', 'NM1_G', 'NM1_S', 'NM1_B'] + ['dummy'] * 1015  # 1020 total
stoi = { device: i for i, device in enumerate(devices) }
encode = lambda s: [stoi.get(c, 0) for c in s]

if train_data.dtype == object:
    print("Processing object array with for loop...")
    all_encoded = []
    for i, sequence in enumerate(train_data):
        if i % 10000 == 0:
            print(f"Processing sequence {i}/{len(train_data)}")
        all_encoded.append(encode(sequence))
        if i >= 100:  # 100개만 테스트
            break

processing_time = time.time() - start_time
print(f"MultiGPU style processing time (100 sequences): {processing_time:.2f} seconds")

# 추정 전체 시간
estimated_total = processing_time * (len(train_data) / 100)
print(f"Estimated total time for all {len(train_data)} sequences: {estimated_total:.1f} seconds ({estimated_total/60:.1f} minutes)")