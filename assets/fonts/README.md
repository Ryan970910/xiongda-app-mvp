# 站点字体
本站将界面固定文字所需的字形保存为本地 WOFF2。每套界面的标题字体、按钮、图表和数字可在 `type.css` 中核对。所有字体在用户浏览器本地加载。

| 文件 | 字体来源 |
| --- | --- |
| body | [LXGW Neo XiHei](https://github.com/lxgw/LxgwNeoXiHei) |
| qing | [ZCOOL QingKe HuangYou](https://github.com/google/fonts/tree/main/ofl/zcoolqingkehuangyou) |
| smile | [Smiley Sans Oblique](https://github.com/atelier-anchor/smiley-sans) |
| ink | [Liu Jian Mao Cao](https://github.com/google/fonts/tree/main/ofl/liujianmaocao) |
| happy | [ZCOOL KuaiLe](https://github.com/google/fonts/tree/main/ofl/zcoolkuaile) |
| reed | [Long Cang](https://github.com/google/fonts/tree/main/ofl/longcang) |
| pixel | [Fusion Pixel](https://github.com/TakWolf/fusion-pixel-font) |
| brush | [Ma Shan Zheng](https://github.com/google/fonts/tree/main/ofl/mashanzheng) |
| carve | [ZCOOL XiaoWei](https://github.com/google/fonts/tree/main/ofl/zcoolxiaowei) |
| sweep | [Zhi Mang Xing](https://github.com/google/fonts/tree/main/ofl/zhimangxing) |
| mono | [Space Mono](https://github.com/google/fonts/tree/main/ofl/spacemono) |
| number | [Barlow Condensed Black](https://github.com/google/fonts/tree/main/ofl/barlowcondensed) |
| segments | 为本站凭证金额绘制的七段数字，包含小数、千分位与人民币符号 |

本目录的第三方字体子集经 FontTools 筛选字形、重新命名和 WOFF2 封装。第三方字体的署名及适用的授权全文见 [LICENSES.txt](./LICENSES.txt)。

`body.woff2` 的派生名称为 YWS Office，遵循 IPA Font License v1.0。要替换为未修改的原字体，可从[原作者发行页](https://github.com/lxgw/LxgwNeoXiHei/releases)或[原字库发行包](https://www.npmjs.com/package/@fontpkg/lxgw-neo-xi-hei/v/1.110.0)取得 LXGWNeoXiHei.ttf，放在本目录，将 `type.css` 中对应的 src 改为该 TTF 路径和 `format("truetype")`。IPA 原始字库及再发行信息也可从[IPA 字体下载页](https://moji.or.jp/ipafont/)取得。该子集直接从原字体生成，保留字形轮廓。
