# Shift Alarm Holidays

排班闹钟 iPhone App 的中国法定节假日和调休工作日数据源。

## 安全边界

- 只接受 `www.gov.cn` 国务院政策文件库中的正式通知。
- 自动任务只创建 Pull Request，不直接修改线上数据。
- 合并前必须通过格式、日期、冲突和 SHA-256 校验。
- App 应先下载到临时区域，全部校验成功后再原子替换旧数据。
- 本仓库不保存用户排班、闹钟、工时或任何个人数据。

## 目录

```text
holidays/                 已审核的年度数据
schema/                   JSON 数据协议
scripts/                  检测、解析、校验和清单生成脚本
tests/                    历史通知解析测试
.github/workflows/        自动检测、验证和 GitHub Pages 发布
manifest.json             App 更新入口
```

## 本地验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_manifest.py
python3 scripts/validate_holidays.py
```

## App 接入

App 每天最多请求一次：

```text
https://lang68745-spec.github.io/shift-alarm-holidays/manifest.json
```

只有 `version` 或 `sha256` 发生变化时才下载对应年度文件。更新失败时继续使用上一个有效版本。

