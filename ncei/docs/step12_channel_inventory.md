# Step 12：全球船测测深数据下载渠道盘点

日期：2026-09-03

## 范围与证据规则

本报告只盘点船载单波束或多波束实测水深。GEBCO、卫星反演水深以及只提供汇编格网而不能确认船测来源记录的产品，不计作可新增船测数据。每个来源区分本次实际访问验证与来源文档声称；没有带 URL 的数量记为 `unknown`。

## 本地基线

- NCEI Marine Trackline：本地 5,550 条唯一航迹。来源：[Step 11 本地清单](step11_archive_gap_report.md)。
- JAMSTEC：任务给定基线为 255 个唯一航次 ID，原始量约 2,805,756,150 个测深点。核对后，**255 只对应第一份源 zip，不是两份本地包的全量航次数**；全语料审核记录为 763 个 subzip、649 个 `cruise_id_guess` 和 5,140 个 `.dat` 文件。来源：[JAMSTEC 来源说明](../../jamstec/SOURCE.md)与[本地航次审核](../../jamstec/multibeam/docs/%E8%88%AA%E6%AC%A1%E6%B8%85%E5%8D%95_%E5%8D%8F%E4%BD%9C%E8%80%85%E5%AE%A1%E6%A0%B8.md)。后文保留“255”以对应任务给定基线，但下一轮差集必须使用全语料的规范化航次 ID，不能把 255 当作本地总量。
- MRAR：本地 113,356,582 个清洗后测深点；交接材料没有原始机构 README，来源链不透明，不把它视作独立于其他归档的已知来源。来源：[MRAR 来源说明](../archive/zhoushuai_processed_M/SOURCE.md)。

## LDEO MGDS / GMRT

- **实际访问验证（2026-09-03）**：先后通过 `127.0.0.1:2081` 请求检索页、通过 `127.0.0.1:2082` 请求 MGDS 首页，两次都在 TLS 建连阶段失败，未取得 HTTP 响应或页面内容。按每源两次请求上限停止。
- **持有范围与量级**：`unknown`。本次未取得可引用的官方目录数字，不能用 GMRT 格网覆盖量替代原始船测航次或测线数量。
- **获取方式**：`unknown`。
- **与本地重合可能性**：可能重合，属于推断。NCEI 现有目录和缺口表含 Lamont-Doherty Earth Observatory 机构记录，但本次没有取得 MGDS 航次清单，不能计算重合数量。
- **许可**：`unknown`。
- **入口**：[MGDS / GMRT](https://www.marine-geo.org/)（本次访问失败）。

## PANGAEA

- **实际访问验证（2026-09-03）**：`127.0.0.1:2084` 连接超时；改用 `127.0.0.1:2085` 访问 [PANGAEA 的 bathymetry multibeam 检索页](https://www.pangaea.de/?q=bathymetry%20multibeam)，HTTP 200。页面 HTML 为前端检索壳，结果列表未在服务端 HTML 中给出，因此没有可引用的命中数。
- **文档声称**：该页说明其服务用于归档、出版和分发有地理定位的地球系统研究数据。这能证明它是数据集级发布渠道，不能证明其中全部是船测，也不能给出船测航次总量。
- **持有范围与量级**：范围为跨学科地球系统研究数据，其中检索词可指向测深资料；船载单波束/多波束数据集数与点数均为 `unknown`。
- **获取方式**：按数据集检索和分发；本次没有实际打开具体数据集下载链接，是否可直接匿名下载记为 `unknown`。
- **与本地重合可能性**：可能重合。该库按研究数据集和航次分散发布，未取得可与本地 Survey ID 或 JAMSTEC 航次号直接对照的总清单。
- **许可**：页面提供 Terms of use 链接，但本次未打开；具体数据集许可为 `unknown`，下一轮必须逐 DOI 核对。

## EMODnet

- **实际访问验证（2026-09-03）**：[EMODnet Bathymetry](https://emodnet.ec.europa.eu/en/bathymetry) 与其 [SeaDataNet CDI 调查数据检索入口](https://cdi-bathymetry.seadatanet.org/search) 均经 `127.0.0.1:2085` 返回 HTTP 200。CDI 页面显示登录和 Dataset basket，但目录内容由脚本加载，本次未取得调查数据集总数。
- **文档声称**：EMODnet 将“bathymetric survey data”明确为单波束和多波束调查的高分辨率数据集，并称目录汇集了 **65 个以上数据提供方**的资料；调查数据不限于欧洲海区，而是欧洲提供方管理的全球各海区数据。来源：[EMODnet Bathymetry](https://emodnet.ec.europa.eu/en/bathymetry)。
- **持有范围与量级**：提供方超过 65 个；船测调查数据集数、航次数、点数和字节数均为 `unknown`。2024 DTM、HR-DTM、GEBCO 补空和卫星反演层不计入本任务的船测量。
- **获取方式**：通过 SeaDataNet CDI 检索单个调查数据集并提交 shopping request；官方页面称多数调查数据集需要所有者批准。公开 DTM 可直接下载，但它不属于本任务的原始船测渠道。
- **与本地重合可能性**：高。EMODnet 是多提供方元数据与申请入口，且与 IHO DCDB 通过 Web 服务互联；未取得航次级清单，不能与本地 NCEI、JAMSTEC 或 MRAR 定量去重。
- **许可**：CDI 元数据公开且可免费使用；高分辨率调查数据受各所有者政策约束，多数需批准，不能统一视为开放许可。来源同上。

## BODC

- **实际访问验证（2026-09-03）**：旧检索 URL 返回 HTTP 301；按其 Location 访问 [BODC 新检索入口](https://www.bodc.ac.uk/resources/search/) 返回 HTTP 200。页面确认站内有 Cruise inventory、BODC request (ASCII) format 和数据持有概览入口，但检索只接受表单 POST，本次 GET 没有生成 `multibeam bathymetry` 结果。
- **持有范围与量级**：可确认 BODC 按航次编目海洋数据；无法在两次请求内确认船载单波束/多波束子集，相关数据集数、航次数、点数和字节数均为 `unknown`。页面所列 GEBCO gridded bathymetry 不计入本任务。
- **获取方式**：站点存在航次清单和 BODC 数据申请格式；测深数据究竟可直接下载还是需申请为 `unknown`。
- **与本地重合可能性**：可能重合，属于推断。NCEI 目录已有 UK Hydrographic Office 等英国机构记录，但没有取得 BODC 测深清单，不能量化。
- **许可**：`unknown`。

## IFREMER / SHOM

- **实际访问验证（2026-09-03）**：[IFREMER 海洋数据门户](https://data.ifremer.fr/) 与 [data.shom.fr](https://data.shom.fr/) 均经 `127.0.0.1:2085` 返回 HTTP 206 的限长响应。IFREMER 页面给出 Centre de données 和 Recherche de données 入口；SHOM 返回地图应用壳，页面描述其提供海洋、海岸和海洋学物理环境参考数据。两页都没有在服务端 HTML 中列出船测目录。
- **持有范围与量级**：IFREMER 船载单波束/多波束数据和 SHOM 原始测深的航次、调查、测线、点数及字节数均为 `unknown`。SHOM 地图或格网产品不能据此计作原始船测。
- **获取方式**：IFREMER 可从门户进入数据检索；SHOM 可从地图门户进入数据服务。原始测点是直接下载、申请还是订购，本次均未验证，记为 `unknown`。
- **与本地重合可能性**：可能与 EMODnet/SeaDataNet 及 NCEI 的欧洲机构资料重合，属于推断；没有航次级清单，无法量化。
- **许可**：两者均为 `unknown`；不能从门户可访问推断原始测深可自由再分发。

## Geoscience Australia / AusSeabed

- **实际访问验证（2026-09-03）**：[AusSeabed](https://www.ausseabed.gov.au/) 经 `127.0.0.1:2085` 返回 HTTP 403；[Geoscience Australia Marine 门户](https://portal.ga.gov.au/persona/marine) 返回 HTTP 200，但服务端 HTML 是门户应用壳，没有列出测深记录。
- **文档声称**：GA Marine 门户页面元数据称其提供对 Geoscience Australia 数据及其他公开数据源的访问。这不是船测子集说明，也没有证明原始声呐文件可下载。
- **持有范围与量级**：船载单波束/多波束调查数、航次数、点数和字节数均为 `unknown`；AusSeabed 汇编表面或地图层不计作原始船测。
- **获取方式**：GA Web 门户；原始船测是直接下载、申请还是线下交付，`unknown`。
- **与本地重合可能性**：可能与 NCEI 收录的澳大利亚航次及其他全球归档重合，属于推断；无航次级清单可供去重。
- **许可**：`unknown`；“公开数据源”描述不能替代具体数据集许可。

## NIWA / LINZ

- **实际访问验证（2026-09-03）**：[NIWA 站内检索](https://niwa.co.nz/search?query=bathymetry%20data%20index) 经 `127.0.0.1:2085` 返回 HTTP 206 的限长响应；页面有 Oceans 下的 Bathymetry 分类和 Voyages 入口，但该 GET 参数没有生成具体结果。[LINZ Data Service Hydrographic 入口](https://data.linz.govt.nz/layers/category/hydrographic/) 返回 HTTP 200，页面载入数据服务应用配置，但未在服务端 HTML 中给出水深数据集清单。
- **持有范围与量级**：可确认 NIWA 网站按 bathymetry 和航次组织入口、LINZ 有空间数据服务；船测调查数、航次数、测线数、点数和字节数均为 `unknown`。
- **获取方式**：NIWA 航次/主题入口与 LINZ 数据服务；原始单波束或多波束是否可匿名直接下载，本次未验证，记为 `unknown`。
- **与本地重合可能性**：可能与 NCEI、PANGAEA 或其他航次库重合，属于推断；没有取得可对照的航次清单。
- **许可**：LINZ 页面提供 “Licensing and using data” 链接，但本次未打开具体数据集或许可正文；记为 `unknown`，不能把站点级 Crown copyright 信息当作全部数据的统一下载许可。

## 中国国家海洋科学数据中心

- **实际访问验证（2026-09-03）**：[国家海洋科学数据中心首页](https://mds.nmdis.org.cn/) 和 [“多波束 测深”检索页](https://mds.nmdis.org.cn/pages/totalSearch.html?query=%E5%A4%9A%E6%B3%A2%E6%9D%9F%20%E6%B5%8B%E6%B7%B1) 经 `127.0.0.1:2085` 均返回 HTTP 206 的限长响应。页面是前端应用壳，显示搜索、登录和注册入口，但检索结果没有写入服务端 HTML。
- **持有范围与量级**：本次不能确认公开目录里船载单波束/多波束测深的具体记录；数据集数、航次数、测线数、点数和字节数均为 `unknown`。前端未返回结果不能解释为没有数据。
- **获取方式**：门户检索入口已验证；是否可直接下载、需在线申请或需线下联系，`unknown`。页面存在登录/注册不能证明所有下载都要求登录。
- **与本地重合可能性**：`unknown`。本地 MRAR 的交接说明缺原始机构 README，不能把它与该中心建立或排除来源关系。
- **许可**：`unknown`。

## GEBCO / Seabed 2030 contributors 名单

- **实际访问验证（2026-09-03）**：[Seabed 2030 Our Partners](https://seabed2030.org/our-partners/) 经 `127.0.0.1:2085` 返回 HTTP 200。页面名单可见 NOAA、EMODnet、Geoscience Australia、GMRT、LINZ、Scripps 和 WHOI 等机构。对猜测的 GEBCO 旧 contributors URL 的第二次请求返回 HTTP 404；404 页导航给出当前 [Our Data Contributors](https://www.gebco.net/about-us/acknowledgements/our-data-contributors) 路径，但本次未再请求正文。
- **文档声称**：Seabed 2030 页面称项目有 **200 多个伙伴、数据贡献方和支持者，来自 50 个国家**。来源：[Seabed 2030 Our Partners](https://seabed2030.org/our-partners/)。该数字混合数据贡献方、技术伙伴和支持者，不能解释为 200 多个原始船测归档。
- **持有范围与量级**：这是来源发现名单，不是可直接下载的原始船测目录。各贡献方实际提供的航次、测线、点数与公开字节数均为 `unknown`；GEBCO 格网本身排除。
- **获取方式**：沿名单逐机构回查原始持有者；名单页本身不提供统一原始测点下载。
- **与本地重合可能性**：明确很高。名单同时包含本报告已查的 NOAA/NCEI 体系、EMODnet、GA、GMRT、LINZ 等，不能把名单各项简单相加。
- **许可**：名单无统一数据许可；必须回到贡献机构或具体数据集核对。GEBCO 产品许可不能代替原始船测许可。

## JAMSTEC 公开库未纳入部分

- **实际访问验证（2026-09-03）**：旧 DARWIN 英文入口返回 HTTP 301；按 Location 访问当前 [JAMSTEC DARWIN](https://www.godac.jamstec.go.jp/darwin/en/) 经 `127.0.0.1:2085` 返回 HTTP 206 的限长响应。页面明确提供 Cruise Information 检索，维护公告也明确提到 file download function。
- **文档声称**：DARWIN 发布 JAMSTEC 研究船和研究潜器取得的观测数据及样品信息。页面列出的平台包括 NATSUSHIMA、KAIYO、YOKOSUKA、MIRAI、KAIREI、CHIKYU、KAIMEI、SHINSEI MARU、HAKUHO MARU 以及多种潜器。来源：[JAMSTEC DARWIN](https://www.godac.jamstec.go.jp/darwin/en/)。
- **持有范围与量级**：DARWIN 的机构/平台范围明确宽于本地材料所述约 2000–2015 的语料。任务给定的 255 是第一份源 zip 的唯一航次 ID 数；本地全语料另有 649 个 `cruise_id_guess`。可确认本地不是 JAMSTEC 公开库的全平台清单；额外平台中有多少航次包含可下载单波束或多波束测深，以及点数/字节数，均为 `unknown`。
- **获取方式**：航次检索和网站文件下载；本次没有下载文件，也没有验证是否所有文件都能匿名取得。
- **与本地重合可能性**：高且部分确定。KAIYO、MIRAI、KAIREI 已在本地；NATSUSHIMA、YOKOSUKA、CHIKYU、KAIMEI、SHINSEI MARU 等平台及 2015 年后的航次是下一轮差集候选，仍需按航次号和数据类型去重。
- **许可**：页面提供 Terms and Conditions、Data Policy 和 Site Policy 链接，但本次未打开正文；具体再利用许可为 `unknown`。

## 冰山评估

### 能确认的外部未纳入量

这里的“未纳入”指尚未进入本地 L1 点、L2 格子和 L3 航线来源清单；已下载到临时原始目录但尚未加工的数据也算未纳入。

| 证据层 | 相对本地基线仍未纳入的量 | 能否与其他行相加 |
| --- | ---: | --- |
| NCEI Marine Trackline 同一目录内的已知水深航迹缺口 | 706 个 Survey ID；目录估算 XYZ 为 3,329,184,900 字节。其中 R2R 已取得 167 个文件、779,562,732 字节，但尚未进入本地三层产品，因此仍属未纳入 | 可作为同一目录内的明确缺口；不能与 R2R 再加一次。来源：[NCEI catalog API](https://www.ngdc.noaa.gov/next-web/docs/guide/catalog.html) 与 [ordering API](https://www.ngdc.noaa.gov/next-web/docs/guide/ordering.html)，实际盘点见 `ncei/docs/step11_archive_gap_report.md` |
| IHO DCDB 众包测深 | 2,339,461,220 个 soundings | 不能与 NCEI、EMODnet 或各贡献方相加；可能重复，且公开字段无 uncertainty、accuracy、QC 或 quality。来源：[pointstore API 文档](https://raw.githubusercontent.com/CI-CMG/pointstore-api-docs/main/pointstore_api.md) |
| NCEI MBBDB | `unknown`；当前航次清单、格式和总字节数尚未盘点 | 不能估算。它是当前最直接的全球多波束目录缺口 |
| EMODnet 船测调查层 | 65 个以上数据提供方；调查数据集总数、点数和字节数 `unknown` | 不能把提供方数当航次数，也不能与各国家库相加。来源：[EMODnet Bathymetry](https://emodnet.ec.europa.eu/en/bathymetry) |
| JAMSTEC DARWIN 相对任务给定的 255 航次基线 | 公开平台范围比本地宽；新增含测深的航次数和字节数 `unknown`。本地核对同时表明 255 只是第一份源 zip 的计数，全语料已有 649 个 `cruise_id_guess` | 需要先统一本地航次 ID，再按航次号和数据类型去重。来源：[JAMSTEC DARWIN](https://www.godac.jamstec.go.jp/darwin/en/) 与[本地航次审核](../../jamstec/multibeam/docs/%E8%88%AA%E6%AC%A1%E6%B8%85%E5%8D%95_%E5%8D%8F%E4%BD%9C%E8%80%85%E5%AE%A1%E6%A0%B8.md) |
| MGDS、PANGAEA、BODC、IFREMER/SHOM、GA/AusSeabed、NIWA/LINZ、中国国家海洋科学数据中心 | 全部为 `unknown` | 本轮只能确认部分入口存在，不能推算量级 |

### 对“是否只是冰山一角”的回答

**按渠道和持有机构覆盖看，是。** 本地基线集中在 NCEI Marine Trackline、JAMSTEC 的一批历史航次和来源不透明的 MRAR；本轮已经确认同一 NCEI 目录仍有 706 个水深航迹缺口，MBBDB 尚未盘点，JAMSTEC 公开目录的平台范围也宽于本地。EMODnet 又连接 65 个以上欧洲数据提供方，Seabed 2030 的 200 多个伙伴、数据贡献方和支持者来自 50 个国家，说明全球来源网络远超当前三个本地来源。后一个数字只证明发现空间大，不代表 200 多个可下载船测库。来源：[Seabed 2030 Our Partners](https://seabed2030.org/our-partners/)。

**按去重后、许可允许、能进入当前产品的实测数据量，不能量化“冰山一角”所占比例。** 除 NCEI 的 706 个缺口和 DCDB 的 2,339,461,220 个众包点外，其余来源没有取得可引用总量；跨库航次重复尚未排除。DCDB 又缺逐轨质量字段，[EMODnet](https://emodnet.ec.europa.eu/en/bathymetry) 也明确说明多数高分辨率调查数据需要所有者批准。因此当前不能声称“本地只占全球 10%”或给出任何完成率。

### 下一轮真盘点顺序

1. **NCEI MBBDB**：先取完整 cruise/file 清单、格式、字节数和直接下载状态，再与本地 17 个 NCEI 多波束文件及 Marine Trackline Survey ID 交叉核对。本地文件数来源：[数据产品规范第 1.1 节](../../docs/%E6%95%B0%E6%8D%AE%E4%BA%A7%E5%93%81%E8%A7%84%E8%8C%83%E4%B8%8E%E4%B8%8B%E6%B8%B8%E6%8E%A5%E5%85%A5.md)。它最接近现有入库结构，能最快给出新增多波束量。
2. **JAMSTEC DARWIN**：先把本地 763 个 subzip 规范化为航次 ID，解决 255 与 649 两种计数的定义差异；再导出 DARWIN 全航次与观测数据类型，只保留含单波束/多波束测深的航次并做差。该源的重合键最清楚。
3. **EMODnet/SeaDataNet CDI**：取得可机读的 survey metadata 清单，记录 provider、cruise、instrument、空间范围、access restriction 和下载状态；先算元数据差集，不提交批量申请。
4. **MGDS/GMRT**：代理访问恢复后，盘点 cruise 与原始 swath/track 数据目录，并与 NCEI 的 Lamont-Doherty、R2R、Scripps 和 WHOI 航次去重。
5. **国家/机构库**：依次盘点 GA/AusSeabed、NIWA/LINZ、IFREMER/SHOM、BODC 和中国国家海洋科学数据中心。先找可导出的调查清单；只能看格网或需人工订购时，记录元数据规模和限制，不下载产品。
6. **PANGAEA**：用 API 或无脚本检索导出 DOI 级候选，再以 cruise/vessel/DOI 去重。它适合补零散科研航次，不宜先按关键词命中数估算总量。

GEBCO/Seabed 2030 贡献方名单只作下一批机构发现索引；NOAA OCS S3 的格网产品不进入本任务；IHO DCDB CSB 在缺少逐轨质量字段时保留为单独的低信息量船测层，不与有仪器、航次和质检元数据的归档混合。
