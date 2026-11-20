# 澄川平行样脉冲复核

白班接纳员保存计数器导出的原始批和出处。质控员选定规程，从权威库的一次读截面签发固定表。夜班拿到完整件后可以关闭发行库，以同一张表上的部分格目标办理回填。下一班从当前截面签发新表，再用旧表号、回执号和槽历史核对前后结果。

## 运行

要求 Python 3.11 和标准库 SQLite。控制台在物化工程时提供标准核验入口。演示在测试临时目录中建立两个 SQLite 文件，实际关闭和重开发行库及权威库。

```sh
python3 -B check_project.py
python3 -B demo.py
```

## 公开接口

| 调用 | 输入与结果 |
| --- | --- |
| `source.database.open_source_database(path)` | 打开或初始化权威库，返回 SQLite 连接。重开保留全部持久记录。 |
| `sheets.archive.open_issuance_database(path)` | 打开或初始化独立的规程和固定表档案。调用方负责关闭两个连接。 |
| `intake.batches.import_batch(source, batch_id, rows)` | 接纳一个非空有序批。行字段为 `slot`、`capacity`、`count` 和 `origin`，出处字段为 `export` 和从 1 起算的 `line`。槽号全权威库唯一。返回 `ImportedBatch`，其中 `rows` 为最初接纳行。 |
| `intake.batches.read_original_batch(source, batch_id)` | 领取原始批、行序、首版计数与出处。原批同内容重放返回这份记录，同批号异内容或跨批占用同一槽号报冲突。 |
| `source.slots.read_slot(source, slot_id, revision=None)` | 当前或指定历史修订，返回 `SlotView`，包含容量、计数、原出处和可选回执号。修订号按槽从 1 起算。 |
| `rules.catalog.register_recipe(issuer, recipe_id, cells)` | 保存非空有序格。每格提交 `name` 与 `slots`，引用数为一或二。重复引用同一槽时按出现次数相加。重放同定义可重用，异定义同号报冲突。 |
| `sheets.issue.issue_sheet(issuer, source, batch_id, recipe_id)` | 在该批的一次读截面上计算，返回 `IssuedSheet`，其中 `sheet` 为已签发业务对象，`piece` 为完整固定件字节。 |
| `sheets.accept.read_sheet(subject, archive=None)` | `subject` 可为完整件字节、固定表对象，或配合 `archive=` 使用的表号。返回 `FixedSheet`，有序显示在 `displays`，槽证据与格引用在 `basis`。 |
| `corrections.apply.submit_edit(source, piece, targets)` | 接收完整件或固定表对象，以及非空的格名到整数目标映射。成功返回 `EditReceipt`，无解或多解分别返回 `ResolutionStatus.NO_SOLUTION` 或 `MULTIPLE`。 |
| `corrections.receipts.read_receipt(source, receipt_id)` | 返回原表号、目标、受影响槽以及本次实际提交的修订和计数。 |

计量以脉冲个数为单位。计数和容量须是真正的整数，计数闭区间为 `0 ≤ count ≤ capacity`。和格可大于任一单槽容量。整单采用同一原槽的一个计数，所有通过共享槽连通的未编辑格保持发行值。两个不相连的组同时提交时，任一组无解即整单无解。全部组唯一才可更正。受影响组的每个槽都必须匹配发行时的父批、修订、计数和容量，同值回填也形成新修订。无关槽的修订不影响受理。

非法字段、未知目标格和无效固定件引发 `ValueError`。批号或槽号冲突为 `BatchConflict`，规程同号异定义为 `RecipeConflict`。缺少指定记录引发 `KeyError`，源证据过期或不匹配引发 `StaleRevision`，SQLite 提交失败保留原错误。写入失败时原件、历史、当前指针和此前成果可按其原号领取，失败操作没有新成果或成功回执。

## 固定件 V1

固定件是 UTF-8 JSON 对象。外层包含 `version`、`sheet_number`、`batch_id`、`recipe_id`、`displays` 和 `basis`。编号和修订号使用正 SQLite 整数。`displays` 是有序 `{name, count}` 数组。`basis.cells` 是同序 `{name, slots}` 数组。`basis.slots` 以原槽号为键，每项含 `count`、`capacity` 和 `revision`。计量字段是小写十六进制整数文本，零写为 `"0"`，负数在允许的字段带 `-`，无前导零。所有公共 Python 计量值均为 `int`。完整件在离线接纳时检查引用闭合、容量范围和显示重算一致性。接收端以指定件为依据，写回端在提交边界复核权威槽证据。表号只在配套发行库中使用，权威库和发行库按同一实验室成对部署。
