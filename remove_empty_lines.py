import os

input_file = r"D:\学校工作\2026资料\03论文评阅\世界科技研究与发展\0428\审稿意见.txt"
output_file = r"D:\学校工作\2026资料\03论文评阅\世界科技研究与发展\0428\审稿意见_去空行.txt"

# 读取文件内容
with open(input_file, "r", encoding="gbk") as f:
    lines = [line for line in f if line.strip()]

# 写入新文件（不带末尾换行符）
with open(output_file, "w", encoding="gbk") as f:
    f.writelines(lines)

print(f"处理完成！已去除空行，共保留 {len(lines)} 行")
