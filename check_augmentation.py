import numpy as np
import os

def check_augmentation_count(dataset_range_start=0, dataset_range_end=100):
    """Dataset 번호별로 증강된 시퀀스 개수를 확인합니다."""
    
    print(f"Dataset {dataset_range_start}번부터 {dataset_range_end}번까지 증강 현황 확인\n")
    print("Dataset번호 | 시퀀스 개수 | 파일 상태")
    print("-" * 40)
    
    augmentation_stats = {
        'total_datasets': 0,
        'found_files': 0,
        'missing_files': 0,
        'augmentation_counts': {}
    }
    
    for i in range(dataset_range_start, dataset_range_end + 1):
        augmentation_stats['total_datasets'] += 1
        
        # 파일 경로 생성
        sequence_file = f"/home/seungmin.kim/AnalogGenie/Dataset/{i}/Sequence_total{i}.npy"
        
        if os.path.exists(sequence_file):
            try:
                # npy 파일 로드
                sequences = np.load(sequence_file)
                num_sequences = sequences.shape[0] if len(sequences.shape) >= 1 else 0
                
                # 통계 업데이트
                augmentation_stats['found_files'] += 1
                if num_sequences not in augmentation_stats['augmentation_counts']:
                    augmentation_stats['augmentation_counts'][num_sequences] = 0
                augmentation_stats['augmentation_counts'][num_sequences] += 1
                
                print(f"Dataset{i:3d}  |    {num_sequences:3d}개    | ✓ 존재")
                
            except Exception as e:
                print(f"Dataset{i:3d}  |     오류     | ✗ 로드 실패: {str(e)[:20]}...")
                augmentation_stats['missing_files'] += 1
        else:
            print(f"Dataset{i:3d}  |     없음     | ✗ 파일 없음")
            augmentation_stats['missing_files'] += 1
    
    print("\n" + "="*50)
    print("📊 증강 현황 요약")
    print("="*50)
    print(f"전체 확인 대상: {augmentation_stats['total_datasets']}개")
    print(f"파일 존재: {augmentation_stats['found_files']}개")
    print(f"파일 없음/오류: {augmentation_stats['missing_files']}개")
    
    if augmentation_stats['augmentation_counts']:
        print(f"\n🔢 증강 개수별 분포:")
        for count, datasets in sorted(augmentation_stats['augmentation_counts'].items()):
            print(f"  {count:3d}배 증강: {datasets:2d}개 데이터셋")
    
    return augmentation_stats

# 실행
if __name__ == "__main__":
    stats = check_augmentation_count(0, 100)