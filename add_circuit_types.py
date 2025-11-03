import numpy as np
import os
from tqdm import tqdm

def get_circuit_category(dataset_number):
    """
    데이터셋 번호에 따른 회로 카테고리를 반환합니다.
    data_categorization.md를 기반으로 분류합니다.
    """
    if 281 <= dataset_number <= 336 or 1781 <= dataset_number <= 2180:
        return "CIRCUIT_Opamp"
    elif 632 <= dataset_number <= 635 or 1045 <= dataset_number <= 1080:
        return "CIRCUIT_Comparator"
    elif (403 <= dataset_number <= 437) or (521 <= dataset_number <= 544) or (640 <= dataset_number <= 646) or (1109 <= dataset_number <= 1190):
        return "CIRCUIT_Oscillator"
    elif 98 <= dataset_number <= 159 or 604 <= dataset_number <= 613 or 834 <= dataset_number <= 867:
        return "CIRCUIT_Current_Mirror"
    elif 69 <= dataset_number <= 97 or 614 <= dataset_number <= 621:
        return "CIRCUIT_Differential_Amp"
    elif (461 <= dataset_number <= 492) or (1081 <= dataset_number <= 1090):
        return "CIRCUIT_LNA"
    elif (494 <= dataset_number <= 520) or (1091 <= dataset_number <= 1099):
        return "CIRCUIT_Mixer"
    elif 2181 <= dataset_number <= 2630:
        return "CIRCUIT_LDO"
    elif (368 <= dataset_number <= 384) or (624 <= dataset_number <= 627) or (1461 <= dataset_number <= 1780):
        return "CIRCUIT_Bandgap_Ref"
    elif 1 <= dataset_number <= 68 or 822 <= dataset_number <= 833 or 669 <= dataset_number <= 687:
        return "CIRCUIT_Single_Stage_Amp"
    elif 578 <= dataset_number <= 592 or 1100 <= dataset_number <= 1108:
        return "CIRCUIT_Power_Amp"
    elif 726 <= dataset_number <= 737:
        return "CIRCUIT_Voltage_Regulator"
    elif 768 <= dataset_number <= 788 or 651 <= dataset_number <= 651:
        return "CIRCUIT_Filter"
    elif 2631 <= dataset_number <= 3502:
        return "CIRCUIT_Switched_Cap"
    else:
        return "CIRCUIT_General"

def add_circuit_type_to_sequences(dataset_start=1, dataset_end=3502, backup=True):
    """
    기존 Sequence_total{number}.npy 파일들에 Circuit Type 토큰을 추가합니다.
    
    Args:
        dataset_start: 시작 데이터셋 번호
        dataset_end: 끝 데이터셋 번호 
        backup: 기존 파일 백업 여부
    """
    
    stats = {
        'processed': 0,
        'skipped': 0,
        'errors': 0,
        'circuit_types': {}
    }
    
    print(f"Dataset {dataset_start}번부터 {dataset_end}번까지 Circuit Type 토큰 추가 시작")
    print(f"백업 {'활성화' if backup else '비활성화'}")
    
    for i in tqdm(range(dataset_start, dataset_end + 1), desc="Processing datasets"):
        sequence_file = f"Dataset/{i}/Sequence_total{i}.npy"
        
        # 파일이 존재하는지 확인
        if not os.path.exists(sequence_file):
            stats['skipped'] += 1
            continue
        
        try:
            # 기존 시퀀스 로드
            sequences = np.load(sequence_file)
            original_shape = sequences.shape
            
            # 이미 Circuit Type이 추가되었는지 확인 (길이가 1025인지)
            if len(sequences.shape) == 2 and sequences.shape[1] == 1025:
                # 첫 번째 시퀀스의 첫 번째 토큰이 CIRCUIT_로 시작하는지 확인
                if len(sequences) > 0 and str(sequences[0][0]).startswith('CIRCUIT_'):
                    print(f"Dataset {i}: 이미 Circuit Type 추가됨 - 스킵")
                    stats['skipped'] += 1
                    continue
            
            # 회로 카테고리 결정
            circuit_type = get_circuit_category(i)
            stats['circuit_types'][circuit_type] = stats['circuit_types'].get(circuit_type, 0) + 1
            
            # 백업 생성
            if backup:
                backup_file = f"Dataset/{i}/Sequence_total{i}_backup.npy"
                if not os.path.exists(backup_file):
                    np.save(backup_file, sequences)
            
            # 새로운 시퀀스 배열 생성
            new_sequences = []
            
            for seq in sequences:
                # 기존 시퀀스가 1025 길이인 경우
                if len(seq) == 1025:
                    # TRUNCATE 위치 찾기
                    truncate_pos = None
                    for j, token in enumerate(seq):
                        if token == 'TRUNCATE':
                            truncate_pos = j
                            break
                    
                    if truncate_pos is not None:
                        # 실제 시퀀스 부분과 TRUNCATE 부분 분리
                        actual_seq = seq[:truncate_pos].tolist()
                        
                        # Circuit Type을 맨 앞에 추가
                        new_seq = [circuit_type] + actual_seq
                        
                        # 1025로 다시 패딩
                        if len(new_seq) <= 1025:
                            padded_seq = new_seq + ['TRUNCATE'] * (1025 - len(new_seq))
                            new_sequences.append(padded_seq)
                        else:
                            # 길이가 초과하면 마지막 토큰들 제거
                            trimmed_seq = new_seq[:1024] + ['TRUNCATE']
                            new_sequences.append(trimmed_seq)
                    else:
                        # TRUNCATE가 없는 경우 (전체가 실제 시퀀스)
                        actual_seq = seq.tolist()
                        new_seq = [circuit_type] + actual_seq[:-1]  # 마지막 토큰 하나 제거해서 공간 확보
                        new_sequences.append(new_seq)
                else:
                    # 다른 길이의 시퀀스는 그냥 Circuit Type 추가
                    new_seq = [circuit_type] + seq.tolist()
                    if len(new_seq) <= 1025:
                        padded_seq = new_seq + ['TRUNCATE'] * (1025 - len(new_seq))
                        new_sequences.append(padded_seq)
                    else:
                        trimmed_seq = new_seq[:1025]
                        new_sequences.append(trimmed_seq)
            
            # 새로운 배열로 변환
            new_sequences_array = np.array(new_sequences, dtype=object)
            
            # 파일 저장
            np.save(sequence_file, new_sequences_array)
            
            stats['processed'] += 1
            
            # 진행 상황 출력 (매 100개마다)
            if i % 100 == 0:
                print(f"Dataset {i}: {original_shape} -> {new_sequences_array.shape}, Circuit Type: {circuit_type}")
        
        except Exception as e:
            print(f"Dataset {i} 처리 중 에러: {e}")
            stats['errors'] += 1
            continue
    
    # 최종 통계 출력
    print("\n" + "="*50)
    print("Circuit Type 추가 완료!")
    print("="*50)
    print(f"처리된 파일: {stats['processed']}개")
    print(f"스킵된 파일: {stats['skipped']}개") 
    print(f"에러 발생: {stats['errors']}개")
    
    print(f"\n📊 Circuit Type별 분포:")
    for circuit_type, count in sorted(stats['circuit_types'].items()):
        print(f"  {circuit_type}: {count}개")
    
    return stats

if __name__ == "__main__":
    # 작은 범위로 테스트
    print("🧪 테스트 실행: Dataset 1-100")
    test_stats = add_circuit_type_to_sequences(1, 100, backup=True)
    
    # 전체 실행할지 확인
    if test_stats['processed'] > 0:
        response = input(f"\n테스트 성공! 전체 데이터셋(1-3502)을 처리하시겠습니까? (y/N): ")
        if response.lower() == 'y':
            print("🚀 전체 실행 시작")
            full_stats = add_circuit_type_to_sequences(1, 3502, backup=True)
        else:
            print("테스트만 완료되었습니다.")
    else:
        print("❌ 테스트에서 처리된 파일이 없습니다. 설정을 확인해주세요.")