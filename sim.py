import matplotlib.pyplot as plt
import random
import matplotlib
import numpy as np
from datetime import datetime, timedelta
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

class StudentBrain:
    """学生大脑情绪模拟器"""
    
    def __init__(self, base_arousal=0.5, base_valence=0.5):
        self.arousal = base_arousal  # 唤醒度 (0-1)
        self.valence = base_valence  # 愉悦度 (0-1)
        self.stress_level = 0.2     # 压力水平
        self.fatigue = 0.1          # 疲劳度
        self.weekly_stress = 0.0    # 一周累积压力
        self.semester_stress = 0.0  # 学期累积压力
        self.adaptation_level = 1.0 # 适应程度(学期初低,逐渐提高)
        
    def step(self, inputs):
        """根据输入更新情绪状态"""
        # 获取输入参数
        task_pressure = inputs.get('task_pressure', 0)
        fatigue = inputs.get('fatigue', 0)
        dopamine = inputs.get('dopamine', 0)
        control_sense = inputs.get('control_sense', 0)
        social_factor = inputs.get('social_factor', 0)
        achievement = inputs.get('achievement', 0)
        weekend_factor = inputs.get('weekend_factor', 0)
        season_factor = inputs.get('season_factor', 0)
        exam_factor = inputs.get('exam_factor', 0)
        holiday_factor = inputs.get('holiday_factor', 0)
        
        # 更新压力累积
        self.weekly_stress += task_pressure * 0.1
        self.semester_stress += task_pressure * 0.02
        self.weekly_stress = max(0, min(1, self.weekly_stress))
        self.semester_stress = max(0, min(1, self.semester_stress))
        
        # 更新唤醒度 (受多因子影响)
        arousal_change = (task_pressure * 0.3 + dopamine * 0.4 - fatigue * 0.3 
                         - self.weekly_stress * 0.1 + exam_factor * 0.3 - holiday_factor * 0.2)
        self.arousal = max(0, min(1, self.arousal + arousal_change * 0.3))
        
        # 更新愉悦度 (受多因子影响)
        valence_change = (control_sense * 0.3 + social_factor * 0.2 + achievement * 0.4 
                         - task_pressure * 0.2 + weekend_factor * 0.3 + season_factor * 0.2 
                         - exam_factor * 0.2 + holiday_factor * 0.4)
        self.valence = max(0, min(1, self.valence + valence_change * 0.3))
        
        # 添加适应性调整(学期初压力大,后期适应)
        adaptation_effect = (1 - self.adaptation_level) * 0.1
        self.arousal += adaptation_effect
        self.valence -= adaptation_effect
        
        # 青春期随机波动
        self.arousal += random.uniform(-0.05, 0.05)
        self.valence += random.uniform(-0.05, 0.05)
        
        # 确保在有效范围内
        self.arousal = max(0, min(1, self.arousal))
        self.valence = max(0, min(1, self.valence))
        
        return self.arousal, self.valence
    
    def reset_weekly_stress(self):
        """周末重置累积压力"""
        self.weekly_stress *= 0.3
    
    def update_adaptation(self, week_num):
        """更新学期适应程度"""
        # 学期初适应度低,逐渐提高,期末又下降
        if week_num <= 4:
            self.adaptation_level = 0.3 + week_num * 0.15  # 前4周逐渐适应
        elif week_num <= 14:
            self.adaptation_level = 0.9  # 中期适应良好
        else:
            self.adaptation_level = 0.9 - (week_num - 14) * 0.1  # 期末疲劳
    
    def reset_semester(self):
        """学期结束重置"""
        self.semester_stress = 0.0
        self.adaptation_level = 1.0

# 定义学期重要时间节点
semester_events = {
    1: "学期开始,新环境适应",
    3: "第一次月考",
    6: "适应期结束",
    8: "期中考试周",
    9: "期中考试后调整",
    12: "学期中期疲劳",
    15: "期末复习开始",
    16: "期末考试周",
    17: "期末考试",
    18: "学期结束,寒假开始"
}

def get_season_factor(week_num):
    """根据周数计算季节因子"""
    # 假设学期从9月开始(秋季学期)
    # 9-11月: 秋季, 12-1月: 冬季
    if week_num <= 8:  # 9-10月
        return 0.1  # 秋高气爽,心情较好
    elif week_num <= 14:  # 11月
        return 0.0  # 深秋,情绪中性
    else:  # 12月-1月
        return -0.1  # 冬季,情绪略低

def get_exam_factor(week_num):
    """获取考试压力因子"""
    exam_weeks = {3: 0.3, 8: 0.6, 16: 0.8, 17: 0.9}  # 考试周压力
    return exam_weeks.get(week_num, 0)

def get_holiday_factor(week_num):
    """获取假期期待因子"""
    if week_num >= 17:  # 接近寒假
        return 0.6
    elif week_num >= 15:  # 期末临近,期待假期
        return 0.3
    else:
        return 0

def generate_week_schedule(week_num, student_brain):
    """生成一周的详细时间安排"""
    # 基础课程安排
    base_schedule = {
        '周一': [
            {"time": "07:00 起床", "task_pressure": 0.3, "fatigue": 0.6},
            {"time": "09:00 语文课", "task_pressure": 0.4, "control_sense": 0.5},
            {"time": "12:00 午餐", "social_factor": 0.7, "dopamine": 0.6},
            {"time": "15:00 数学课", "task_pressure": 0.7, "control_sense": 0.3},
            {"time": "18:00 晚自习", "task_pressure": 0.6, "fatigue": 0.4},
            {"time": "21:00 作业", "task_pressure": 0.7, "fatigue": 0.5}
        ],
        '周二': [
            {"time": "07:00 起床", "task_pressure": 0.4, "fatigue": 0.5},
            {"time": "09:00 英语课", "task_pressure": 0.6, "control_sense": 0.4},
            {"time": "12:00 午餐", "social_factor": 0.6, "dopamine": 0.5},
            {"time": "15:00 体育课", "dopamine": 0.8, "achievement": 0.6, "social_factor": 0.7},
            {"time": "18:00 晚自习", "task_pressure": 0.5, "fatigue": 0.4},
            {"time": "21:00 作业", "task_pressure": 0.6, "fatigue": 0.5}
        ],
        '周三': [
            {"time": "07:00 起床", "task_pressure": 0.4, "fatigue": 0.4},
            {"time": "09:00 物理课", "task_pressure": 0.8, "control_sense": 0.2},
            {"time": "12:00 午餐", "social_factor": 0.6, "dopamine": 0.5},
            {"time": "15:00 化学课", "task_pressure": 0.7, "control_sense": 0.3},
            {"time": "18:00 晚自习", "task_pressure": 0.7, "fatigue": 0.5},
            {"time": "21:00 作业", "task_pressure": 0.8, "fatigue": 0.6}
        ],
        '周四': [
            {"time": "07:00 起床", "task_pressure": 0.5, "fatigue": 0.6},
            {"time": "09:00 历史课", "task_pressure": 0.5, "control_sense": 0.5},
            {"time": "12:00 午餐", "social_factor": 0.5, "dopamine": 0.4},
            {"time": "15:00 美术课", "dopamine": 0.9, "achievement": 0.7, "control_sense": 0.8},
            {"time": "18:00 晚自习", "task_pressure": 0.6, "fatigue": 0.5},
            {"time": "21:00 作业", "task_pressure": 0.7, "fatigue": 0.6}
        ],
        '周五': [
            {"time": "07:00 起床", "task_pressure": 0.4, "fatigue": 0.7},
            {"time": "09:00 地理课", "task_pressure": 0.4, "control_sense": 0.6},
            {"time": "12:00 午餐", "social_factor": 0.8, "dopamine": 0.7},
            {"time": "15:00 班会", "social_factor": 0.6, "dopamine": 0.5},
            {"time": "17:00 放学", "weekend_factor": 0.8, "dopamine": 0.8},
            {"time": "20:00 周末前夜", "weekend_factor": 0.9, "dopamine": 0.9}
        ],
        '周六': [
            {"time": "09:00 睡懒觉", "weekend_factor": 0.7, "dopamine": 0.6, "fatigue": 0.2},
            {"time": "11:00 户外活动", "weekend_factor": 0.9, "dopamine": 0.9, "achievement": 0.7},
            {"time": "14:00 朋友聚会", "weekend_factor": 0.8, "social_factor": 0.9, "dopamine": 0.8},
            {"time": "16:00 娱乐时间", "weekend_factor": 0.7, "dopamine": 0.7},
            {"time": "19:00 家庭时间", "weekend_factor": 0.6, "social_factor": 0.7},
            {"time": "22:00 自由时间", "weekend_factor": 0.9, "dopamine": 0.8}
        ],
        '周日': [
            {"time": "10:00 睡懒觉", "weekend_factor": 0.6, "dopamine": 0.5},
            {"time": "12:00 家庭聚餐", "weekend_factor": 0.7, "social_factor": 0.8},
            {"time": "15:00 做作业", "task_pressure": 0.6, "weekend_factor": 0.2},
            {"time": "18:00 准备明天", "task_pressure": 0.5, "weekend_factor": 0.1},
            {"time": "20:00 周日忧郁", "task_pressure": 0.7, "weekend_factor": -0.2},
            {"time": "22:00 早睡", "task_pressure": 0.4, "fatigue": 0.6}
        ]
    }
    
    # 添加学期特殊因子
    season_factor = get_season_factor(week_num)
    exam_factor = get_exam_factor(week_num)
    holiday_factor = get_holiday_factor(week_num)
    
    # 为每个时间点添加学期因子
    for day in base_schedule:
        for time_slot in base_schedule[day]:
            time_slot["season_factor"] = season_factor
            time_slot["exam_factor"] = exam_factor  
            time_slot["holiday_factor"] = holiday_factor
            
            # 考试周特殊调整
            if exam_factor > 0:
                time_slot["task_pressure"] = min(1.0, time_slot.get("task_pressure", 0) + exam_factor)
                time_slot["fatigue"] = min(1.0, time_slot.get("fatigue", 0) + exam_factor * 0.5)
    
    return base_schedule

# 创建学生大脑实例
student_brain = StudentBrain(base_arousal=0.6, base_valence=0.7)

# 生成整个学期的情绪数据
semester_data = []
week_summaries = []

print("正在生成学期情绪数据...")

for week_num in range(1, 19):  # 18周学期
    print(f"生成第{week_num}周数据...")
    
    # 更新适应程度
    student_brain.update_adaptation(week_num)
    
    # 生成本周安排
    week_schedule = generate_week_schedule(week_num, student_brain)
    
    week_emotions = []
    week_stress_sum = 0
    
    # 模拟本周每一天
    for day, schedule in week_schedule.items():
        for event in schedule:
            A, V = student_brain.step(event)
            
            emotion_entry = {
                "Week": week_num,
                "Day": day,
                "Time": event["time"],
                "Arousal": round(A, 2),
                "Valence": round(V, 2),
                "WeeklyStress": round(student_brain.weekly_stress, 2),
                "SemesterStress": round(student_brain.semester_stress, 2),
                "Adaptation": round(student_brain.adaptation_level, 2)
            }
            
            semester_data.append(emotion_entry)
            week_emotions.append(emotion_entry)
            week_stress_sum += student_brain.weekly_stress
    
    # 周末重置压力
    if week_num % 1 == 0:  # 每周重置
        student_brain.reset_weekly_stress()
    
    # 计算本周摘要
    week_avg_arousal = sum([e["Arousal"] for e in week_emotions]) / len(week_emotions)
    week_avg_valence = sum([e["Valence"] for e in week_emotions]) / len(week_emotions)
    week_max_stress = max([e["WeeklyStress"] for e in week_emotions])
    
    week_summary = {
        "week": week_num,
        "avg_arousal": round(week_avg_arousal, 2),
        "avg_valence": round(week_avg_valence, 2),
        "max_stress": round(week_max_stress, 2),
        "semester_stress": round(student_brain.semester_stress, 2),
        "adaptation": round(student_brain.adaptation_level, 2),
        "event": semester_events.get(week_num, "正常学习周")
    }
    
    week_summaries.append(week_summary)

print(f"学期数据生成完成! 共{len(semester_data)}个数据点")

# 数据可视化
# 1. 学期整体趋势图
weeks = [w["week"] for w in week_summaries]
week_arousal = [w["avg_arousal"] for w in week_summaries]
week_valence = [w["avg_valence"] for w in week_summaries]
week_stress = [w["semester_stress"] for w in week_summaries]
week_adaptation = [w["adaptation"] for w in week_summaries]

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(20, 12))

# 子图1: 学期情绪趋势
ax1.plot(weeks, week_arousal, marker='o', label="平均唤醒度", linewidth=3, markersize=6, color='red')
ax1.plot(weeks, week_valence, marker='s', label="平均愉悦度", linewidth=3, markersize=6, color='blue')
ax1.set_xlabel("学期周数", fontsize=12)
ax1.set_ylabel("情绪数值", fontsize=12)
ax1.set_title("学期18周情绪变化趋势", fontsize=14, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend(fontsize=11)

# 标注重要事件
event_weeks = [1, 3, 8, 16, 17, 18]
for week in event_weeks:
    if week <= len(weeks):
        ax1.axvline(x=week, color='gray', linestyle='--', alpha=0.5)
        ax1.text(week, 0.9, semester_events[week][:6], rotation=90, fontsize=8)

# 子图2: 压力累积和适应度
ax2.plot(weeks, week_stress, marker='^', label="学期累积压力", linewidth=3, color='orange')
ax2.plot(weeks, week_adaptation, marker='v', label="适应程度", linewidth=3, color='green')
ax2.set_xlabel("学期周数", fontsize=12)
ax2.set_ylabel("数值", fontsize=12)
ax2.set_title("压力累积与适应程度变化", fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3)
ax2.legend(fontsize=11)

# 子图3: 每周情绪分布箱型图
week_nums = list(range(1, 19))
arousal_data = []
valence_data = []

for week in week_nums:
    week_data = [e for e in semester_data if e["Week"] == week]
    arousal_data.append([e["Arousal"] for e in week_data])
    valence_data.append([e["Valence"] for e in week_data])

ax3.boxplot(arousal_data, positions=week_nums, widths=0.6)
ax3.set_xlabel("学期周数", fontsize=12)
ax3.set_ylabel("唤醒度分布", fontsize=12)
ax3.set_title("每周唤醒度分布情况", fontsize=14, fontweight='bold')
ax3.grid(True, alpha=0.3)

# 子图4: 情绪状态分类统计
emotion_counts = {"兴奋开心": 0, "疲惫低落": 0, "心情愉快": 0, "精神紧张": 0, "压力很大": 0, "情绪平静": 0}

for entry in semester_data:
    if entry["Arousal"] > 0.7 and entry["Valence"] > 0.7:
        emotion_counts["兴奋开心"] += 1
    elif entry["Arousal"] < 0.4 and entry["Valence"] < 0.4:
        emotion_counts["疲惫低落"] += 1
    elif entry["Valence"] > 0.7:
        emotion_counts["心情愉快"] += 1
    elif entry["Arousal"] > 0.7:
        emotion_counts["精神紧张"] += 1
    elif entry["SemesterStress"] > 0.6:
        emotion_counts["压力很大"] += 1
    else:
        emotion_counts["情绪平静"] += 1

emotions = list(emotion_counts.keys())
counts = list(emotion_counts.values())
colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#ff99cc', '#c2c2f0']

ax4.pie(counts, labels=emotions, autopct='%1.1f%%', colors=colors, startangle=90)
ax4.set_title("学期情绪状态分布", fontsize=14, fontweight='bold')

plt.tight_layout()
plt.show()

# 打印学期摘要报告
print("\n" + "="*60)
print("🎓 学期情绪分析报告")
print("="*60)

print(f"\n📊 整体统计:")
semester_avg_arousal = sum([e["Arousal"] for e in semester_data]) / len(semester_data)
semester_avg_valence = sum([e["Valence"] for e in semester_data]) / len(semester_data)
max_semester_stress = max([e["SemesterStress"] for e in semester_data])

print(f"学期平均唤醒度: {semester_avg_arousal:.2f}")
print(f"学期平均愉悦度: {semester_avg_valence:.2f}")
print(f"最大学期压力: {max_semester_stress:.2f}")

print(f"\n📅 关键时期分析:")
for week_summary in week_summaries:
    if week_summary["week"] in semester_events:
        print(f"第{week_summary['week']:2d}周 - {week_summary['event']:<15} | "
              f"愉悦度: {week_summary['avg_valence']:.2f} | "
              f"压力: {week_summary['semester_stress']:.2f} | "
              f"适应: {week_summary['adaptation']:.2f}")

print(f"\n🎯 情绪状态分布:")
total_points = len(semester_data)
for emotion, count in emotion_counts.items():
    percentage = (count / total_points) * 100
    print(f"{emotion}: {count}次 ({percentage:.1f}%)")

print(f"\n📈 学期发展趋势:")
early_valence = sum([w["avg_valence"] for w in week_summaries[:6]]) / 6
mid_valence = sum([w["avg_valence"] for w in week_summaries[6:12]]) / 6  
late_valence = sum([w["avg_valence"] for w in week_summaries[12:]]) / 6

print(f"学期初期愉悦度 (1-6周): {early_valence:.2f}")
print(f"学期中期愉悦度 (7-12周): {mid_valence:.2f}")
print(f"学期后期愉悦度 (13-18周): {late_valence:.2f}")
print(f"中期相比初期: {mid_valence - early_valence:+.2f}")
print(f"后期相比中期: {late_valence - mid_valence:+.2f}")