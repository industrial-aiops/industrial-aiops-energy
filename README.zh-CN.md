<!-- mcp-name: io.github.industrial-aiops/iaiops-energy -->

# industrial-aiops-energy — 能源版（变电 / 电力）

[English](README.md) · **中文**

[Industrial-AIOps](https://github.com/industrial-aiops/industrial-aiops) 的**能源版**，
已拆分为独立仓库：面向**变电站 / 电力调度**远动协议的**只读** OT 连接器，构建在
**`iaiops.core`** 之上。

- **IEC 60870-5-104**（`c104`）— RTU / 变电站遥测
- **DNP3 / IEEE 1815**（`pydnp3`）— 子站监视
- **IEC 61850 MMS**（`pyiec61850`，仅 Linux wheel）— 变电站 IED 读取

它复用基础包共享的**治理 harness**（审计 / 预算 / 风险分级 / 回滚）、**跨协议智能层**
（在归一化的 ISA-95/18.2 模型上做数据流 / 报警 / OEE / 停机 RCA），以及 MCP server 基础设施
——本仓只新增三个能源连接器 + 各自的会话构造器 + MCP 工具。**读优先：不暴露任何控制方向的写。**

当前版本：**0.1.11**（要求 `iaiops>=0.20.3,<1.0`）。

**0.1.11 新增** — **三条监视路径首次全部纳入 CI 门禁**，被跳过的 live 测试现在会让构建
**失败**而不是变绿。DNP3 是最后一个holdout：`pip install pydnp3` 在任何当前 Linux 上都失败，
于是本仓沿袭了生态里那句"在托管 runner 上构建不了"，`tests/test_dnp3_live.py` 每次构建都被跳过。
**它并非构建不了**——opendnp3 本身编译干净，烂掉的是 2019 年的绑定层，三处机械修复即可，
现已脚本化在 `scripts/build_pydnp3.sh` 并在真实 GitHub runner 上运行。同时继承 `iaiops` 0.20.3
的两个治理修复（pin 上调）：**失败**的调用不再被审计成成功（这一点此前还会在每次失败时误导
pattern 熔断器），以及 runaway 守卫现在能看见一个调用方无限重试同一个拒绝。

**0.1.10** — 一个**从基础包继承的安全修复**：本版镜像的三个出口工具
（`stream_publish`、`stream_publish_event`、`historian_push`）会把凭据——NATS auth token、
TSDB 密码——**明文写进审计日志**，而 `audit_forward` 会把那一行发往配置的 SIEM。它们定义在
`iaiops` 里，本版无法单独修复；pin 上调到 `iaiops>=0.20.2`，并新增契约测试：整个注册工具面
若再出现未声明的凭据参数，构建即失败。**如果你曾把 token 或 historian 密码传给这些工具，请
轮换它**，并检查已有审计行。能源连接器本身不接受任何凭据参数。

**0.1.9** — 每个工具都带上 MCP `ToolAnnotations` 提示（`readOnlyHint` / `destructiveHint` /
`openWorldHint`），且是**从 `@governed_tool` harness 推导**而非手写，因此客户端无需解析
`[READ]`/`[WRITE]` docstring 标记就能区分「监视读」和「会动手的工具」。落到线上是 59 个工具、
55 个只读、**0 个破坏性**——本版不暴露控制方向，而这一点现在由测试强制而非仅写在文档里。
它们是**提示不是门禁**：MCP 规范禁止依赖 annotations 做安全决策，强制仍在 `@governed_tool`。
基础包 pin 上调到 `iaiops>=0.20.1`，提示推导从 `mcp_server.hints` 导入而非在此重复实现。

**0.1.8** — 基础包的 `IAIOPS_READ_ONLY` 开关在 iaiops 0.19.0 中**已移除**（读写授权是调用方的
决定——agent 判断 / 账号管理——不是 tap 的事；每个工具都经基础 `@governed_tool` harness 治理
并留审计），本版一并去掉。**保留 `IAIOPS_NO_EGRESS=1`** ——这是数据外泄 / 气隙维度的开关，
在注册阶段就把数据外送类工具从 `list_tools()` 里扣掉。本版跑自己的 `FastMCP` 实例，所以该开关
接在自己的 `main()` 上；否则 `IAIOPS_NO_EGRESS=1` 仍会暴露从基础智能层镜像过来的
`historian_push`、`rca_narrate` 和 `stream_publish*`。能源连接器本身仅监视，不受影响。

**0.1.6** — 对三个只读连接器做了一轮**审计加固**：DNP3 不再把离线子站报成在线、也不再返回
残缺的整体召唤数据库；IEC-61850 增加了有界的连接 / 请求超时，并停止在失败时伪造
`0.0`/空成功；变电分析器不再把单个断路器跳闸称作"选择性跳闸"；测试隔离 `IAIOPS_HOME`；
基础包 pin 上调到 `iaiops>=0.14` 以应用治理端点作用域修复。详见 `CHANGELOG.md` §0.1.6。
（0.1.5 验证了 IEC-104 监视路径——Linux 容器内真实 `c104` 客户端↔服务端往返，
`tests/test_iec104_live.py`。）**物理 RTU / IED 仍未验证。**

自 0.1.3 起，server 拥有**独立的 MCP 身份**——`iaiops-energy-mcp` 运行专用的
`FastMCP("iaiops-energy")` 实例，带能源专属指令（IEC-104 / DNP3 / IEC-61850，读优先，
无控制 / 操作），基础跨协议智能层工具镜像其上——外加**版本专属 skill**
（`skills/iaiops-energy/SKILL.md`，对注册工具面做过防漂移测试）与**协议一致性契约测试**
（每个工具必须带治理标记、`[READ]` 式风险标签、`Args:` 段，以及规范的 `{error, hint}`
错误形状；任一注册工具缺治理标记，server 拒绝启动）。

## 🧪 测试与共创

**变电站现场的测试反馈是这个包最缺的东西。** IEC-104 / DNP3 / IEC-61850 三条监视路径均已对
真实库（c104 / opendnp3 / libiec61850 的进程内 server）做过 loopback 往返验证，**且三条都在
每次 CI 真实执行**——跳过会让构建失败，而不是让它变绿。（2026-08-01 起：此前 DNP3 的证据只是
2026-07-02 的一次手工运行，因为 `pydnp3` 被认为在托管 runner 上无法构建；那个结论是错的，
见下方 `scripts/build_pydnp3.sh`。）

但 **真实 RTU / IED 物理设备一律未验证**——如果你能在授权的测试环境里对真实变电设备跑一遍
`iaiops doctor`，我们非常想听结果。经你验证的设备会署名写进支持矩阵。反馈（协议 + 设备型号 +
`iaiops doctor` 输出）请走基础仓的置顶 issue：
👉 [industrial-aiops#28 — Call for field-testing partners (v0.10.0)](https://github.com/industrial-aiops/industrial-aiops/issues/28)

## 为什么单独一个仓

能源面向不同的买家（电力 / 变电站），有更重的平台相关依赖（`pyiec61850` 是仅 Linux 的 SWIG
wheel；`pydnp3` 要编译原生扩展），且有自己的合规面（**电力监控系统安全防护**）。拆出来能让
基础包保持轻量。方案见基础仓的 `docs/ENERGY-SPINOUT.md`。

## 安装

```bash
pip install iaiops-energy[energy]      # 三个能源协议全装
pip install iaiops-energy[iec104]      # 只装 IEC-104
```

`iaiops-energy` 会自动拉入 `iaiops`（共享 core）。

## 使用（MCP）

```bash
iaiops-energy-mcp                       # 智能层 + 能源工具，走 stdio
```

在 `~/.iaiops/config.yaml` 里把 target 指向你的变电设备
（`protocol: iec104|dnp3|iec61850`、`host`、`port`、`common_address` / `unit_id`）。

## 边缘部署与生态（edge-native / Margo）

和基础包一样，能源版运行在一台加固、集中管理的**边缘主机**上，作为可移植、受治理的
**边缘应用**——对应 [Margo](https://margo.org/) 边缘互操作角色（不可变主机 · 合规编排器 ·
**iaiops-energy = OT 域应用**），可作为 OCI **Managed Container** 部署（仅出向连到变电
RTU/IED，无入向）。容器 + `margo.org/v1-alpha1` 应用描述骨架在
[`deploy/margo/`](deploy/margo/)；完整对齐说明与诚实的差距分析在基础仓的
[`docs/MARGO-ALIGNMENT.md`](https://github.com/industrial-aiops/industrial-aiops/blob/main/docs/MARGO-ALIGNMENT.md)。
该描述符在每个 PR 上都会对 Margo 公布的 `margo.org/v1-alpha1` LinkML schema 做校验
（CI job `margo-descriptor`）并通过——但**仅是结构合法性**，见
[`deploy/margo/schema/PROVENANCE.md`](deploy/margo/schema/PROVENANCE.md)。

> **诚实状态**：它天然是一个 Margo 边缘应用，但**尚未 Margo 合规**——镜像构建、托管+签名的
> 包、以及公布的一致性测试结果都还是路线图 `⏳`。在那个结果出现之前不做任何合规声明；
> 上面那次 schema 通过**不是**朝它迈出的一步：合规测试套件今天根本跑不了，因为它还不存在
> （`margo` org 下没有 conformance 仓库；截至 2026-01-15，第一个 PR1 纵切还在立项阶段）。

## 验证状态（诚实标注）

和基础仓同一套诚实阶梯。驱动的**编解码 / API 面**已对真实库验证；mock / monkeypatch 的
**单元测试在 CI 里跑**，不需要硬件。一个协议如何被提级，见基础仓的
`docs/PREVIEW-VERIFICATION.md` runbook。

| 协议 | 状态 | CI 覆盖 | 证据 |
| --- | --- | --- | --- |
| **DNP3 / IEEE 1815** | **已验证（监视路径）** | ✅ 每次 push 都跑 ¹ | 对真实 **opendnp3** 子站（`pydnp3`）的主站↔子站往返：`is_online()` 反映真实通道的 `OnStateChange`，`integrity_poll()`（Class 0/1/2/3）返回按类型分组的种子二进制/模拟量/计数器数据库。见 `tests/test_dnp3_live.py`（`@pytest.mark.integration`）。无物理 RTU。 |
| **IEC 60870-5-104** | **已验证（监视路径）** | ✅ 每次 push 都跑 | 对进程内 **`c104`** 服务端的真实客户端↔服务端往返（`tests/test_iec104_live.py` + `tests/iec104_server_harness.py`，`@pytest.mark.integration`，在 Linux 容器内通过）：`iec104_connection_info` 发现种子站点，`iec104_interrogate`（总召唤 / C_IC）返回带品质的种子 `M_ME_NC_1` + `M_SP_NA_1` 点，`iec104_read_point` 读出测量值，非法 IOA 返回 `found=False` 且**不伪造数值**，服务端 ASDU 抓包证明**从未下发任何控制 ASDU**（C_SC / C_DC / C_SE）。`c104` 不提供 macOS wheel，故该测试在 macOS 上跳过（在 CI / Linux 上运行）。无物理 RTU。仅监视 / 只读。 |
| **IEC 61850（MMS）** | **已验证（监视路径）** | ✅ 每次 push 都跑 | 对用 `pyiec61850` 服务端 API 搭起的进程内 **libiec61850** MMS 服务端做真实客户端↔服务端 MMS 往返：`iec61850_device_directory` 列出逻辑设备（并浏览其逻辑节点 / 数据对象），`iec61850_read` 经真实 ISO-on-TCP 返回种子测量值（`TotW.mag.f`，FC `MX`）；非法引用会浮出 MMS 数据访问错误而不是伪造值。见 `tests/test_iec61850_live.py`（`@pytest.mark.integration`，`pyiec61850` / 其服务端 API 缺失时跳过）。无物理 IED。仅读 / 监视——控制 / GOOSE / SV 不在范围内。 |

**¹ 三条监视路径现已全部纳入 CI 门禁**，跳过会让构建失败而不是通过
（`no live protocol test may skip`）。这里以前写的是：*"只有 IEC-104 进了 CI 门禁；DNP3 和
IEC-61850 靠 CI 之外的运行，而不是靠那枚绿色徽章。"* 那句话当时是真的，现在不再是。

DNP3 是最后一个，而它的原因值得记下来，因为此处的旧注释、CI job、以及这份 README——都把同一个
错误结论重复了好几个月：`pip install pydnp3` 在任何当前 Linux 上都失败，于是被当成在托管
runner 上**构建不了**。并非如此。opendnp3 本身编译干净；烂掉的是 2019 年的绑定层。三处机械
修复，不需要给 opendnp3 打任何补丁：

1. 必须装 Python 头文件（`python3-dev`）——没有它构建会死在
   `Python.h: No such file or directory`，"构建不了"看起来就是这个样子；
2. 214 个 vendored 头文件写着 `#include <python2.7/Python.h>`，改写为 `<Python.h>`；
3. vendored 的 pybind11 早于 CPython 3.11（它读 `PyFrameObject` 内部结构，而 3.11 把它变成了
   不透明类型）和 GCC 13（`std::uint16_t` 未包含 `<cstdint>`）——换成 pybind11 v2.13.6。

`scripts/build_pydnp3.sh` 应用这三处并验证 import。双核冷构建约 3 分钟。**这条教训可以推广：
"生态说它构建不了"是一个待验证的说法，不是一个可以继承的结论。**

DNP3 备注：仅只读 / 监视方向（无控制）。它的 `DNP3Manager.Shutdown()` 在长生命周期解释器里
可能阻塞，因此连接器对拆解做了有界处理（`_Pydnp3MasterAdapter.shutdown`），测试则在短生命周期
子进程里驱动整个往返。

## 许可

MIT — © wei。厂商中立、受治理的 Industrial-AIOps 产品线的一部分。
