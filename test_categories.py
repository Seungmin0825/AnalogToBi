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

# 카테고리 분류 테스트
test_cases = [
    (100, 'Current_Mirror'),
    (300, 'Opamp'), 
    (650, 'Comparator'),
    (1800, 'Opamp'),
    (2500, 'LDO'),
    (3000, 'Switched_Cap')
]

print('Dataset | Expected         | Actual')
print('-' * 45)
for num, expected in test_cases:
    actual = get_circuit_category(num)
    status = "✓" if f"CIRCUIT_{expected}" == actual else "✗"
    print(f'{num:7d} | {expected:15s} | {actual:20s} {status}')

print("\n🎯 회로 카테고리 분포 (일부 샘플):")
categories = {}
for i in range(1, 3503, 100):  # 100개씩 샘플링
    cat = get_circuit_category(i)
    categories[cat] = categories.get(cat, 0) + 1

for cat, count in sorted(categories.items()):
    print(f"  {cat}: {count}개")