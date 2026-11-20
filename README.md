# 研务 · 科研财税政务协作

[打开十套可交互设计](https://ryan970910.github.io/xiongda-app-mvp/?edition=scrolltide#designs)。访客可以直接试办，使用虚构客户、订单和项目，完整版将进度保存在各自的浏览器。选集支持双窗试办，两侧各自使用独立的临时数据。

## 设计选集

十套方案从 Scrolltide 的公开案例提取交互与排版思路，为科研财税政务场景原创实现。点击每套方案底部的原作署名可查看参考。网站使用自制图像、自托管中文字体、原创数字字形和原生浏览器控件。

| 方案 | 可以实际尝试 | 风格参考 |
| --- | --- | --- |
| [研发标本台](https://ryan970910.github.io/xiongda-app-mvp/?ui=specimen#dashboard) | 切换已批项目，点选图钉查负责人、周期和预算 | [Fabrica](https://www.scrolltide.co/templates/fabrica) |
| [受理候场线](https://ryan970910.github.io/xiongda-app-mvp/?ui=queue#dashboard) | 拖动票签，切换角色直接接件 | [Standby](https://www.scrolltide.co/templates/standby) |
| [委托陈列馆](https://ryan970910.github.io/xiongda-app-mvp/?ui=arc#dashboard) | 拨开弧形藏册，打开对应委托 | [Oeuvre](https://www.scrolltide.co/templates/oeuvre) |
| [材料印刷间](https://ryan970910.github.io/xiongda-app-mvp/?ui=press#dashboard) | 平移材料拼贴，点选印张查询底稿索引 | [Tinta House](https://www.scrolltide.co/templates/tinta-house) |
| [版本手卷](https://ryan970910.github.io/xiongda-app-mvp/?ui=leaves#dashboard) | 翻动纸页，追溯并打开历史提交版 | [The Long Light](https://www.scrolltide.co/templates/the-long-light) |
| [字模检索室](https://ryan970910.github.io/xiongda-app-mvp/?ui=glyph#dashboard) | 输入客户、事项或材料词片，即时定位记录 | [Lacuna](https://www.scrolltide.co/templates/lacuna) |
| [时限风标](https://ryan970910.github.io/xiongda-app-mvp/?ui=ridge#dashboard) | 拖动刻度或点选日期，查看到期事项 | [ARÊTE](https://www.scrolltide.co/templates/arete) |
| [协办星图](https://ryan970910.github.io/xiongda-app-mvp/?ui=relay#dashboard) | 选择科研或财务节点，回复、关闭补件 | [Synapse](https://www.scrolltide.co/templates/synapse) |
| [凭证显影室](https://ryan970910.github.io/xiongda-app-mvp/?ui=optic#dashboard) | 移动焦环核对金额、期间和凭证，再追溯底稿 | [Ondine](https://www.scrolltide.co/templates/ondine) |
| [政务回廊](https://ryan970910.github.io/xiongda-app-mvp/?ui=court#dashboard) | 点选门洞或滑动回廊，在委托、研究和交付间切换 | [Solano](https://www.scrolltide.co/templates/solano) |

## 试办

顶栏的「业务目录」可打开订单、项目、任务中心和交付归档。「试办角色」可切换承办人、派单经理、主管、复审经理与总监。切换至业务目录中的其他设计可继续查看同一条记录。

在任意工作台底部点「办理示例委托」，作为财务承办人接件、编辑底稿并提交；再以主管和复审经理审核。重大事项还需总监终审。派单经理登记客户确认后，可锁定成果并下载归档 JSON。退回、重提、各次审核和确认信息均可追溯。财务补件可由科研回复，再由财务关闭。

同一订单可多次派发同线任务。立项通过必要的内部末级审核即对财务开放，客户签收在交付时登记。按实际发生额提交费用，无费用项目也可出现在项目汇总中。

## 本地运行

在仓库根目录运行 `python -m http.server 8080`，打开 `http://localhost:8080/`。流程测试使用 `node tests/workflow.mjs`。部署目标是 GitHub Pages 的 main 根目录。字体来源及许可见 [fonts](assets/fonts/README.md)。

本版使用浏览器角色切换、材料索引和按项目费用明细作为演示。大模型接入留待后续。
