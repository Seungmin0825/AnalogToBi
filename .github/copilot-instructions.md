# AnalogGenie AI 코딩 가이드

## 프로젝트 개요
AnalogGenie는 아날로그 회로 설계를 위한 GPT 기반 언어 모델입니다. 회로를 오일러 회로로 표현하고 트랜스포머를 사용해 다음 디바이스 핀을 예측합니다.

## 핵심 아키텍처

### 모델 구조
- **GPT 모델**: `Models/GPT.py` - 회로 시퀀스 예측을 위한 트랜스포머 구현
- **커스텀 토크나이저**: 회로 구성요소가 구조화된 시퀀스로 토크나이징됨
- **훈련 파이프라인**: `Pretrain.py`에서 필터링된 손실 계산과 함께 모델 훈련

### 디바이스 토크나이제이션 시스템
구조화된 명명 규칙을 사용:
- **MOSFET**: `NM1-34`, `PM1-34` (N/P채널 모스펫)
- **BJT**: `NPN1-26`, `PNP1-26` (양극성 접합 트랜지스터)
- **수동소자**: `R1-27` (저항), `C1-15` (커패시터), `L1-23` (인덕터), `DIO1-7` (다이오드)
- **논리 게이트**: `XOR1`, `INVERTER1-10`, `TRANSMISSION_GATE1-12`
- **전원/신호**: `VDD`, `VSS`, `VIN1-10`, `VOUT1-6`, `VREF1-2`
- **핀 접미사**: `_D` (드레인), `_G` (게이트), `_S` (소스), `_B` (바디/벌크)

### 훈련 데이터 형식
- 훈련 시퀀스는 `.npy` 파일로 저장 (`Training.npy`, `Validation.npy`)
- `TRUNCATE` 토큰을 패딩/종료용으로 사용
- 필터링된 손실 계산은 `TRUNCATE` 토큰을 손실에서 제외

## 개발 워크플로우

### 환경 설정
```bash
conda env create -f environment.yml
conda activate AnalogGenie
```

### 데이터 전처리 파이프라인
```bash
python SPICE2GRAPH_compress.py  # SPICE 넷리스트 → 인접 행렬
python Augmentation.py          # 인접 행렬 → 오일러 회로 + 증강
python Stack.py                 # 오일러 회로 → NumPy 배열 스택
```

### 모델 훈련 및 추론
```bash
python Pretrain.py    # 모델 사전훈련
python Inference.py   # 회로 생성 추론
```

### 핵심 하이퍼파라미터
- `block_size = 1024` - 시퀀스 길이
- `batch_size = 64`
- `device = 'cuda:3'` - 특정 GPU 할당
- 검증 개선 시 `{filename}.pth`로 모델 저장

## 코드 패턴 및 관례

### 손실 계산 패턴
항상 표준 및 필터링된 손실을 모두 구현:
```python
# 표준 교차 엔트로피 손실
loss = F.cross_entropy(logits, targets)

# 필터링된 손실 (TRUNCATE 토큰 제외)
truncate_mask = (targets != stoi["TRUNCATE"])
filtered_loss = F.cross_entropy(logits[truncate_mask], targets[truncate_mask])
```

### 디바이스 생성 루프
디바이스 열거에 일관된 패턴 사용:
```python
for prefix in ["NM", "PM"]:
    for i in range(1, 35):
        devices.append(f"{prefix}{i}")
        for base in nm_np_bases:
            devices.append(base.format(f"{prefix}{i}"))
```

### 모델 체크포인트
검증 개선 시에만 모델 상태 저장:
```python
if losses['val'] < val_loss:
    torch.save(model.state_dict(), f"{filename}.pth")
    val_loss = losses['val']
```

## 중요한 구현 세부사항

### 메모리 관리
- 훈련 루프에서 `torch.cuda.empty_cache()` 사용
- 손실 추정 시 `@torch.no_grad()`와 `model.eval()` 필수
- CSV 로깅으로 필터링된/필터링되지 않은 손실 추적
- 재현 가능한 훈련을 위한 고정 시드 `torch.manual_seed(1337)`

### 토크나이저 일관성
모든 스크립트(`Pretrain.py`, `Inference.py`)에서 동일한 디바이스 생성 로직 유지:
- 베이스 네임 정의가 일치해야 함
- 디바이스 범위 (`NM1-34`, `R1-27` 등)가 일치해야 함
- `stoi`/`itos` 매핑 일관성 유지

### GPU 메모리 최적화
- 대용량 어휘(500+ 토큰)를 위한 메모리 최적화
- 특정 GPU 디바이스 할당 (`cuda:3` vs `cuda:0`)
- 배치 크기 및 시퀀스 길이 조정

## 통합 지점

### 파일 구조 의존성
- `Models/GPT.py`에 모델 정의 필요
- 전처리된 `.npy` 배열로 훈련/검증 데이터
- 외부 분석 도구용 CSV 파일을 통한 손실 추적
- `Inference/` 디렉토리에 생성된 회로 시퀀스 저장

### 데이터 흐름
1. SPICE 넷리스트 → `SPICE2GRAPH_compress.py` → 압축된 그래프
2. 압축된 그래프 → `Augmentation.py` → 증강된 오일러 회로
3. 오일러 회로 → `Stack.py` → 훈련용 NumPy 배열
4. NumPy 배열 → `Pretrain.py` → 훈련된 모델 체크포인트
5. 체크포인트 → `Inference.py` → 새로운 회로 생성

이 가이드는 AnalogGenie 프로젝트의 핵심 패턴과 회로 설계 AI 모델의 특수한 요구사항을 다룹니다.