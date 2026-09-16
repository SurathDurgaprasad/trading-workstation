# **Verified Global Market Intelligence Source Map for an Indian Intraday Trading Agent**

## **Executive Summary and Proposed Architecture**

The integration of global macroeconomic intelligence into a deterministic, high-frequency intraday trading agent fundamentally shifts the system from a purely reactive price-action model to a context-aware predictive engine. The Indian equity market does not operate in a vacuum; it is acutely sensitive to external variables such as United States Treasury yields, European Central Bank policy decisions, the Bank of Japan's interest rate mechanics, and global commodity fluctuations. Furthermore, domestic regulatory announcements from the Securities and Exchange Board of India (SEBI) and the Reserve Bank of India (RBI) act as immediate structural catalysts that can instantly alter intraday liquidity and volatility profiles.

The primary engineering challenge in constructing this Market Intelligence Layer lies not in finding news, but in filtering it. Generic financial news platforms introduce unacceptable latency, hallucinated causality, and conflicting sentiment that poison quantitative models. Therefore, this report outlines a strict hierarchy relying predominantly on Tier 1 (Official) and Tier 2 (Institutional Data Provider) sources. By routing pristine, timestamped, and deduplicated event data into a feature generation pipeline, the intelligence layer provides conditional priors to the existing forecasting engine without overriding its autonomy. An external Large Language Model (LLM) is utilized exclusively as a semantic parser and entity extractor, systematically restricted from making or authorizing trade decisions.

Operating from Nanakramguda, Telangana—a critical financial technology hub with proximity to major exchange disaster recovery sites and optimal latency to AWS ap-south-1 infrastructure1—the architecture is designed to capture, parse, and structure data within milliseconds for local feeds, and within seconds for global asynchronous Webhooks and APIs.

The conceptual architecture for this intelligence layer is built upon parallel ingestion streams that normalize disparate data formats into a unified event schema. The ingestion layer utilizes asynchronous fetchers and rate limiters to poll or subscribe to global sources. This raw data flows into a normalization layer where LLM-assisted semantic parsing translates raw text or XML into a standardized schema, mapping entities to their respective International Securities Identification Numbers (ISIN) and National Industrial Classification (NIC) codes. A deterministic deduplication engine utilizing hashing and time-window clustering ensures that redundant news flashes do not artificially inflate event intensity metrics. Verified events are stored in a time-series graph database, which subsequently feeds into the feature generation layer. Here, metrics such as event surprise, velocity, and news intensity are calculated. These features define the current market regime state, providing the existing quantitative forecast engine with essential context to modulate its confidence intervals and position sizing.

## **Master Event Taxonomy and Normalized Schema**

To ensure machine-readability and eliminate semantic ambiguity, all ingested intelligence is forcefully classified into a rigid, hierarchical event taxonomy. This allows the trading engine to process "Federal Reserve hikes rates" and "RBI increases repo rate" through identical mathematical pathways.

The standardized taxonomy includes, but is not limited to, overarching categories such as MACRO\_DATA (encompassing INFLATION.CPI, EMPLOYMENT.PAYROLLS, GDP.GROWTH), MONETARY\_POLICY (capturing RATE\_DECISION and LIQUIDITY\_OPERATION), and REGULATORY\_CHANGE (tracking MARKET\_STRUCTURE and MARGIN\_RULES). Additionally, GOVERNMENT\_POLICY monitors FISCAL\_BUDGET and TARIFFS, while CORPORATE\_ACTION processes EARNINGS\_RELEASE, DIVIDEND, and MERGER\_ACQUISITION. The system also categorizes MARKET\_METRICS like BOND\_YIELDS and COMMODITY\_PRICES, alongside GEOPOLITICAL shifts such as SANCTIONS and TRADE\_RESTRICTION, and unexpected DISRUPTIONS including SUPPLY\_SHOCK and NATURAL\_DISASTER.

Every ingested document, whether it originates from a WebSocket stream or a scraped PDF, must be transformed into a standardized JSON schema. This schema guarantees temporal integrity, separating the publication time from the ingestion time to rigorously prevent look-ahead bias during historical backtesting.

&nbsp;

&nbsp;

&nbsp;

JSON

{  
&nbsp;&nbsp;"event\_id": "8f4b3c2a-9e1d-4b5a-8c3f-2a1d9e4b3c2a",  
&nbsp;&nbsp;"version\_id": 1,  
&nbsp;&nbsp;"source\_name": "NSE Corporate Announcements",  
&nbsp;&nbsp;"source\_tier": 1,  
&nbsp;&nbsp;"published\_at": "2026-09-15T21:21:30Z",  
&nbsp;&nbsp;"effective\_at": "2026-09-16T03:45:00Z",  
&nbsp;&nbsp;"ingested\_at": "2026-09-15T21:21:31Z",  
&nbsp;&nbsp;"region": "IN",  
&nbsp;&nbsp;"country": "India",  
&nbsp;&nbsp;"event\_type": "CORPORATE\_ACTION.MANAGEMENT\_CHANGE",  
&nbsp;&nbsp;"entities": \[{"type": "COMPANY", "id": "NSE:SAAKSHI", "name": "Saakshi Medtech and Panels Limited"}\],  
&nbsp;&nbsp;"sectors": \[{"type": "NIC", "id": "2620", "name": "Manufacture of computers and peripheral equipment"}\],  
&nbsp;&nbsp;"assets": \["EQUITY"\],  
&nbsp;&nbsp;"summary": "Appointment of Mr. Nandkumar Vasant Dhekne as Independent Director.",  
&nbsp;&nbsp;"raw\_reference": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",  
&nbsp;&nbsp;"source\_url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",  
&nbsp;&nbsp;"source\_confidence": 0.99,  
&nbsp;&nbsp;"market\_relevance": 0.35,  
&nbsp;&nbsp;"novelty": 1.0,  
&nbsp;&nbsp;"urgency": 0.5,  
&nbsp;&nbsp;"potential\_direction": "UNKNOWN",  
&nbsp;&nbsp;"potential\_horizon": "SWING",  
&nbsp;&nbsp;"evidence": \["Timestamp verified by Exchange Dissemination Time: 15-Sep-2026 21:21:31"\]  
}

## **Global Financial Information Ecosystem: Regional Source Maps**

The following sections provide an exhaustive inventory of the global financial information ecosystem as of September 2026\. The evaluation strictly discriminates between data that is technically accessible versus data that is legally and commercially viable for automated ingestion.

### **Indian Market, Regulatory, and Government Intelligence**

The Indian equity market is heavily regulated and deeply influenced by central authorities. The National Stock Exchange (NSE) and Bombay Stock Exchange (BSE) provide the underlying market data, while the Reserve Bank of India (RBI) and the Securities and Exchange Board of India (SEBI) dictate monetary conditions and market structure.

&nbsp;

| Source Name | Organization | URL | Tier | Data / Product | Freq | Timestamp | API / Access | Cost | Latency | Legality / ToS |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **NSE MTBT Feed** | NSE India | nseindia.com \[cite: 2\] | 1 | L2/L3 Order Book, Ticks | Real-time | Yes (ms) | Multicast3 | Enterprise | \<1ms (Colo) | Official License |
| **NSE EOD Corporate Announcements** | NSE India | nseindia.com/static/market-data/ | 1 | EOD Announcements | Daily | Yes (Sec) | SFTP5 | ₹5,00,000/yr5 | EOD (20:00 IST) | Official License |
| **RBI CIMS / DBIE** | Reserve Bank of India | data.rbi.org.in \[cite: 6\] | 1 | Repo, Liquidity, FX, Macros | Event | Yes | XBRL / Web7 | Free | Minutes | Permitted |
| **SEBI Circulars** | SEBI | sebi.gov.in \[cite: 8\] | 1 | Regs, F\&O limits, CSCRF | Event | Date only | Web Scraping | Free | Polling delay | Permitted (Monitor) |
| **PIB Press Releases** | Ministry of I\&B | pib.gov.in \[cite: 9, 10\] | 1 | Gov Policy, Budgets | Event | Yes (Min) | RSS10 | Free | Seconds (RSS) | Public Domain |
| **IFSCA / GIFT City** | IFSCA | ifsca.gov.in \[cite: 11\] | 1 | Offshore derivative liquidity | Event | Date only | Web Scraping | Free | Polling delay | Public Domain |
| **PFRDA Circulars** | PFRDA | pfrda.org.in \[cite: 12\] | 1 | Pension flows, NPS rules | Event | Date only | Web Scraping | Free | Polling delay | Public Domain |
| **IRDAI Master Circulars** | IRDAI | irdai.gov.in \[cite: 13\] | 1 | Insurance flows, Guidelines | Event | Date only | Web Scraping | Free | Polling delay | Public Domain |

Relying on the public-facing NSE website for real-time automated intraday trading violates their terms of service and inevitably fails due to severe rate-limiting and aggressive anti-bot CAPTCHA mechanisms. The only engineering-grade route for real-time exchange data is the Multicast Tick By Tick (MTBT) feed, which provides the full order book without the aggregation delays of standard TCP feeds3. However, for corporate filings, the NSE offers an End of Day Corporate Announcement (EOD CA) product delivered via SFTP for an annual fee of ₹5,00,0005. While not suitable for intraday breakout trading, this SFTP feed is critical for generating overnight regime features and calculating the probabilities of morning gap-ups or gap-downs based on verified earnings and board changes.

Regulatory shifts from SEBI require intense monitoring. In recent years, SEBI has implemented stringent cybersecurity frameworks such as the CSCRF (Cybersecurity and Cyber Resilience Framework), fundamentally altering the compliance overhead for brokers15. More critically for an algorithmic agent, SEBI enforces strict algorithmic trading restrictions, capping unapproved retail API orders at less than 10 orders per second (OPS) to curb excessive speculation8. Furthermore, frequent revisions to market-wide position limits (MWPL) and the exclusion of certain stocks from the Futures and Options (F\&O) segment directly impact liquidity and volatility profiles. Scraping the sebi.gov.in/legal/circulars/ endpoint via a polite, rate-limited cron job is essential for detecting these structural market shifts.

The Reserve Bank of India manages its massive economic datasets through the Database on Indian Economy (DBIE) and the newer Centralised Information Management System (CIMS)6. While the DBIE web interface is dynamically loaded and hostile to simple scrapers, the CIMS architecture utilizes the eXtensible Business Reporting Language (XBRL) standard, allowing for highly structured, machine-readable ingestion of liquidity operations, credit growth, and banking system data18. For immediate government policy announcements, the Press Information Bureau (PIB) provides highly reliable RSS feeds that disseminate cabinet decisions, infrastructure project approvals, and sectoral subsidies instantaneously9.

### **United States Market and Macroeconomic Intelligence**

The transmission mechanism from the United States to the Indian equity market is profound. U.S. monetary policy and employment data govern global risk sentiment, transmitting directly to Indian IT exporters through revenue dependency, and to Indian Financials via yield curve differentials and foreign portfolio investor (FPI) flows.

&nbsp;

| Source Name | Organization | URL | Tier | Data / Product | Freq | Timestamp | API / Access | Cost | Rate Limits |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **FRED API** | St. Louis Fed | api.stlouisfed.org/fred \[cite: 20\] | 1 | 800k+ Macro Series, Yields | Event | Yes | REST API21 | Free (Key) | 120 req/min21 |
| **BLS Public Data API v2** | Dept. of Labor | api.bls.gov \[cite: 22\] | 1 | CPI, PPI, Nonfarm Payrolls | Event | Yes | REST API23 | Free (Key) | 500 queries/day24 |
| **BEA API** | Dept. of Commerce | apps.bea.gov/api \[cite: 25\] | 1 | GDP, Corporate Profits | Event | Yes | REST API25 | Free (Key) | 100 req/min |
| **SEC EDGAR API** | U.S. SEC | data.sec.gov/submissions \[cite: 26\] | 1 | 10-K, 10-Q, 8-K filings | Event | Yes | REST API | Free | 10 req/sec |
| **U.S. Treasury** | Dept. of Treasury | home.treasury.gov | 1 | Daily Yield Curve Rates | Daily | Date only | XML / CSV | Free | Generous |

The Federal Reserve Economic Data (FRED) API represents the gold standard for macroeconomic data ingestion. It offers an impeccably documented REST API with a rate limit of 120 requests per minute21. Crucially for algorithmic backtesting, FRED maintains ALFRED (ArchivaL Federal Reserve Economic Data), which provides point-in-time data exactly as it was originally published on a historical date20. Because macroeconomic indicators like GDP and nonfarm payrolls are frequently revised months after their initial release, training a model on the "final" revised data introduces fatal look-ahead bias. The ALFRED API eliminates this risk entirely.

The Bureau of Labor Statistics (BLS) provides a robust v2 API requiring registration, allowing up to 500 daily queries for critical inflation (CPI/PPI) and employment data23. The transmission mechanism for this data is highly deterministic: if U.S. CPI significantly beats consensus estimates, the U.S. 10-Year Treasury Yield spikes as bond markets price in a hawkish Federal Reserve response. This strengthens the U.S. Dollar (DXY), subsequently weakening the Indian Rupee (INR). Consequently, Foreign Portfolio Investors (FPIs) often withdraw capital from emerging markets, leading to immediate sell-offs in the NIFTY Bank index due to imported inflation risks, while simultaneously triggering algorithmic buying in the NIFTY IT index as a weaker INR boosts the realization of dollar-denominated export revenues.

### **European and Asian Market Intelligence**

European demand metrics and Asian monetary policies are secondary but vital drivers for specific Indian sectors, particularly auto-ancillaries, pharmaceuticals, and metals.

&nbsp;

| Source Name | Organization | URL | Tier | Data / Product | Freq | Timestamp | API / Access | Format | Latency |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **ECB Data Portal** | European Central Bank | data-api.ecb.europa.eu \[cite: 28\] | 1 | Policy Rates, EUR FX | Daily | Yes | SDMX 2.1 REST28 | SDMX-JSON29 | EOD (16:00 CET)28 |
| **Eurostat API** | European Commission | ec.europa.eu/eurostat/api | 1 | EU Macro, Inflation | Event | Yes | REST API | JSON | Minutes |
| **BOJ Time-Series** | Bank of Japan | stat-search.boj.or.jp \[cite: 30\] | 1 | JPY Rates, TANKAN | Event | Yes | REST API31 | CSV / JSON | Minutes |
| **PBOC / NBS** | Govt of China | pbc.gov.cn / stats.gov.cn | 1 | CNY Rates, PMI | Event | Date only | Web Scraping | HTML | Polling delay |

The European Central Bank (ECB) Data Portal operates a free, public SDMX 2.1 REST API that updates daily at 16:00 CET, providing pristine structural metadata on policy rates and exchange rates without requiring an API key28. While the SDMX-JSON format demands specialized parsing logic compared to standard REST JSON29, the data is highly authoritative and essential for Indian corporations with massive European exposure.

In Asia, the Bank of Japan's (BOJ) time-series API is a critically underutilized resource30. The global financial ecosystem relies heavily on the Japanese Yen (JPY) carry trade, where institutions borrow cheaply in Yen to invest in higher-yielding emerging market assets, including Indian equities. When the BOJ unexpectedly signals a rate hike, the immediate unwinding of the Yen carry trade causes aggressive, rapid liquidity contractions globally, resulting in sharp intraday sell-offs in Indian mid-cap and small-cap stocks33. Monitoring the BOJ API provides early-warning signals for these macro-liquidity events. Chinese macroeconomic data from the People's Bank of China (PBOC) and the National Bureau of Statistics (NBS) is notoriously opaque, and their websites frequently throttle or block foreign IP addresses. For Chinese data—which dictates the pricing of Indian steel, copper, and chemical sectors—the architecture must rely on Tier 2 data aggregators rather than direct Tier 1 scraping.

### **Geopolitical, Energy, and Commodity Intelligence**

India is heavily dependent on imported energy, making crude oil price fluctuations a primary macroeconomic determinant for domestic inflation and corporate profitability.

| Source Name | Organization | URL | Tier | Data / Product | API / Access | Cost | Market Impact |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **EIA** | U.S. Dept of Energy | api.eia.gov | 1 | Crude Inventories, WTI | REST API v2 | Free (Key) | OMCs, Airlines, Paints |
| **OPEC** | OPEC Secretariat | opec.org | 1 | Production Quotas | Web / PDF | Free | Brent Crude pricing |
| **LME** | London Metal Exchange | lme.com | 2 | Copper, Aluminum, Zinc | Paid API | Expensive | Indian Metal equities |
| **GDELT** | GDELT Project | gdeltproject.org | 4 | Geopolitical tone, Conflict | JSON / CSV | Free | General risk sentiment |

The U.S. Energy Information Administration (EIA) offers a comprehensive v2 API providing weekly U.S. crude inventory data. Unexpected inventory builds or draws instantly impact global Brent and WTI crude benchmarks. The transmission to Indian equities is highly non-linear and requires precise sector mapping. A sudden spike in Brent crude increases input costs for paint manufacturers (like Asian Paints) and aviation fuel costs for airlines (like IndiGo), compressing their operating margins. Conversely, upstream oil explorers (like ONGC) benefit from higher realizations.

Geopolitical developments in Russia/CIS and the Middle East dictate energy supply shocks and shipping lane disruptions. Relying on the Global Database of Events, Language, and Tone (GDELT) provides a massive, automated feed of global news events categorized by tone and actor. However, GDELT operates as a Tier 4 aggregator with an exceptionally high noise-to-signal ratio. It should be used strictly for detecting anomalous spikes in specific regional conflict intensity (e.g., Red Sea shipping halts) rather than as a definitive factual source for trading decisions.

### **Professional News and Institutional Research Providers**

The core engineering reality is that Tier 1 sources are pristine but fragmented. To achieve near-real-time detection of global events, the system must interface with Tier 2 professional aggregators.

&nbsp;

| Provider | Tier | Data / Product | API / Automation | Cost | Scraping Legality | Recommended Usage |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **Trading Economics** | 2 | Global Calendar, Macro, Alerts | WebSocket / REST34 | $149 \- $299/mo34 | API Permitted35 | **High Priority**. Replaces 50+ manual scrapers. |
| **Bloomberg (B-PIPE)** | 2 | Real-time news, ticks, macro | Enterprise FIX / API | $3,000+/mo | Strictly Prohibited | **Avoid initially**. Cost-prohibitive for early-stage. |
| **Reuters (LSEG)** | 2 | Machine Readable News (MRN) | Enterprise API | Custom / High | Strictly Prohibited | **Research only**. Restrictive redistribution limits. |
| **Alpha Vantage** | 4 | Stock/Forex data, Sentiment | REST API | Freemium | API Permitted | **Low Priority**. Redundant if using Dhan/Exchanges. |
| **Institutional (JPM, GS)** | 3 | Macro research, Flow data | PDF / Web Portal | Client Only | Restricted | **Overnight Regime Context**. Separate opinions from facts. |

Trading Economics emerges as the optimal Tier 2 provider for this architecture. For $299/month on the Professional Plan, it provides access to over 20 million economic indicators across 196 countries, delivering live calendar releases and market quotes via a persistent WebSocket connection34. Crucially, the API handles the normalization of actual, previous, and consensus data points for global macroeconomic releases, allowing the system to instantly calculate "Event Surprise" vectors without building and maintaining 50 distinct central bank web scrapers. The API rate limits are manageable (e.g., 1000 rows per request for historical data, 2 requests per second generally)35. Conversely, while Bloomberg B-PIPE and Reuters Machine Readable News are industry standards, their enterprise pricing models and severe legal restrictions regarding algorithmic redistribution make them unsuitable for this stage of system development.

## **Deduplication, Versioning, and Source Reliability**

In a live trading environment, a significant news event (e.g., a sudden regulatory change) will be reported by multiple sources within seconds of each other, often with slight variations, delays, and subsequent corrections. A naive system will ingest these as separate events, artificially spiking the news\_intensity feature and triggering erroneous momentum models.

To counteract this, the ingestion layer must implement a strict Deduplication and Versioning Engine. When a raw document is parsed, the system generates a deterministic semantic hash based on the \[Date\] \+ \[Extracted Entities\] \+ \[Taxonomy Category\]. If two events map to an identical hash within a 15-minute time window, they are clustered under a single event\_id.

The system relies on a dynamic Source Reliability Scoring Framework. The score is not an arbitrary trust rating but an empirical probability of accuracy calculated as:

![][image1]

Where ![][image2] is the Tier Base Score (Tier 1 official sources \= 1.0, Tier 5 social rumors \= 0.2), ![][image3] represents Latency Quality (assessing if the timestamp has second-level precision), and ![][image4] is the Historical Accuracy Rate, defined as the percentage of historical events from this source that did not require subsequent retractions or corrections.

If a Tier 5 source (e.g., a Twitter/X influencer) reports a refinery shutdown, the system creates a temporary event\_id with a low confidence score, which is insufficient to trigger active trading parameters. If a Tier 2 source (e.g., Trading Economics) verifies the shutdown minutes later, the existing event\_id is retained, but the source\_tier is upgraded, pushing the confidence score past the actionable threshold. If a later document explicitly contradicts the initial report, a new version\_id is pushed with a reversal\_flag \= true. The feature generation layer must immediately calculate an "event unwinding" vector, instructing the forecasting engine to reverse any probabilistic adjustments made based on the prior state.

## **LLM Utilization: Boundaries and Semantic Parsing**

The fundamental rule of this architecture is that Large Language Models (LLMs) must never act as the source of truth, nor can they authorize trades. Financial markets require deterministic execution; LLMs introduce probabilistic hallucination and non-deterministic latency.

The LLM is deployed strictly as an asynchronous normalization function within the ingestion layer. When a SEBI PDF or a PIB press release is scraped, it is passed to a lightweight, highly-instructed LLM (such as Claude 3.5 Sonnet or a fine-tuned Llama 3 instance) with a rigid prompt:

*"Extract the regulatory change or corporate action from the provided text. Return a JSON matching the Normalized Event Schema exactly. Do not infer causality. Do not hallucinate entities. If the event type is ambiguous, return 'UNKNOWN'."*

Every claim extracted by the LLM must contain a raw\_reference linking back to the exact paragraph in the source evidence. The LLM is used to map entities to standardized ISINs or NSE tickers and classify the event into the master taxonomy. The LLM distinguishes between a FACT ("The RBI raised the repo rate by 25 basis points") and an INTERPRETATION ("Analysts at JPMorgan believe this will harm credit growth"). The intelligence layer discards the interpretation, passing only the factual vector to the quantitative engine.

## **Market Sentiment and Regime Feature Design**

Translating textual events into numerical arrays for the existing forecasting engine requires moving beyond naive sentiment analysis (e.g., counting "positive" vs. "negative" words). Empirical research on the Indian stock market demonstrates that while aggregate news sentiment significantly influences NIFTY returns, the effect is highly transient and decays rapidly, heavily dominated by algorithmic reactions rather than sustained fundamental shifts36. Furthermore, abnormal shocks in news sentiment—rather than ambient noise—are critical predictors of cumulative market returns and implied volatility38.

The feature generation pipeline must calculate mathematically rigorous metrics:

> 1. **Event Surprise Vector (![][image5])**:  
>    ![][image6]  
>    This standardizes the shock value of macroeconomic data (e.g., RBI rate decisions, US Payrolls) relative to historical volatility.  
> 2. **News Intensity (![][image7])**: A rolling Poisson process count of high-relevance events in the trailing 15, 30, and 60 minutes for a specific sector. GARCH modeling and empirical studies confirm that news arrival clustering directly correlates with localized volatility clustering39. High ![][image7] alerts the trading agent to expanding bid-ask spreads and potential liquidity vacuums.  
> 3. **Cross-Source Confirmation Velocity (![][image8])**:  
>    Measures the time derivative of an event spreading across independent data providers. Rapid propagation indicates high systemic relevance.

These numerical vectors define the **Market Regime State**. Instead of feeding the trading model a continuous, noisy sentiment score, the system categorizes the market into discrete regimes such as MACRO\_RISK\_ON, LIQUIDITY\_SHOCK, or SECTOR\_DISTRESS\_IT. The existing trading agent does not read the news; it reads the regime vector, utilizing it to dynamically adjust position sizing, widen stop-loss parameters, or suspend mean-reversion algorithms during periods of intense structural volatility.

## **Historical Backtesting and Leakage Risks**

A market intelligence layer is utterly useless if it cannot be backtested without look-ahead bias. The system must rigorously preserve the distinction between published\_at (the time the event supposedly occurred), ingested\_at (the time the system actually processed the data), and effective\_at (the time the market structure changes, e.g., a SEBI margin rule taking effect next Monday).

During historical simulation, the backtester must only expose the trading agent to information where ingested\_at ![][image9] the simulated exchange timestamp.

The greatest risk in macroeconomic backtesting is revised data leakage. Economic indicators are continuously revised; using a 2026 dataset to backtest a 2023 trading strategy will inevitably expose the model to final GDP numbers that no trader actually knew in 2023\. The architecture solves this by mandating the use of the FRED ALFRED API for all U.S. macro data, which provides point-in-time exactitude20, and by ensuring the local Event Store operates as an immutable, append-only ledger where corrections are appended as new versions rather than overwriting historical states.

## **API / Automation and Licensing Matrices**

### **Delivery and Technical Automation Matrix**

| Source | Delivery Protocol | Scraping Feasibility | Real-Time Intraday | Historical Archive |
| :---- | :---- | :---- | :---- | :---- |
| **NSE MTBT** | UDP Multicast | N/A (Direct Line) | Milliseconds | Yes (Paid files) |
| **Trading Economics** | WebSocket / REST | API Required | Seconds | Yes (Deep via API) |
| **FRED / BLS** | REST API | Easy | Event-driven (Minutes) | Yes (Decades) |
| **SEBI / RBI** | HTTPS Polling | Medium (Dynamic DOMs) | Polled (1-5 Minutes) | Yes (Web Archives) |
| **PIB Gov** | RSS / Atom | Easy | Seconds (upon push) | Yes (Web Archives) |
| **ECB / BOJ** | REST API (SDMX/JSON) | Easy | Event-driven (Minutes) | Yes (Deep via API) |

### **Commercial Licensing and Compliance Matrix**

* **SAFE FOR AUTOMATION & COMMERCIAL USE**: FRED (Govt Open Data), BLS, SEC EDGAR, PIB (Govt of India), ECB Data Portal.  
* **REQUIRES PAID COMMERCIAL LICENSE**: NSE MTBT (Exchange Data Agreement required for algorithmic execution), NSE EOD CA (₹5,00,000/yr), Trading Economics (Professional Plan $299/mo).  
* **SCRAPING RESTRICTED / UNKNOWN**: SEBI, RBI, IFSCA. (Web scraping public regulatory PDFs is generally tolerated if polite and rate-limited, but redistribution or packaging as a commercial data feed requires legal clearance).  
* **NOT SUITABLE (Due to ToS)**: Scraping Reuters.com, Bloomberg.com, or live option chains directly from the NSE website without an API agreement.

## **Market Impact Mapping**

The system maps events logically to sectors to avoid hard-coded correlations that fail during regime shifts.

* **EVENT**: *U.S. Federal Reserve unexpectedly raises interest rates.*  
  * *![][image10]* **MACRO FACTOR**: *U.S. Treasury yields spike, USD strengthens globally.*  
  * *![][image10]* **INDIAN SECTOR**: *NIFTY Financial Services, NIFTY IT.*  
  * *![][image10]* **POTENTIAL IMPACT**: *Foreign Portfolio Investors (FPI) trigger capital flight from emerging markets, compressing Bank NIMs due to domestic liquidity tightening. Simultaneously, a stronger USD benefits Indian IT exporters. The agent adjusts short biases on Banks and long biases on IT.*  
* **EVENT**: *SEBI increases margin requirements for specific index options*8.  
  * ![][image10] **MACRO FACTOR**: *Retail liquidity contraction in derivative segments.*  
  * *![][image10]* **INDIAN SECTOR**: *NIFTY Midcaps, Discount Brokerages.*  
  * *![][image10]* **POTENTIAL IMPACT**: *Wider bid-ask spreads and reduced intraday volume. The trading agent tightens execution parameters and reduces algorithmic trading frequency in affected instruments.*  
* **EVENT**: *EIA reports massive unexpected drawdown in crude inventories.*  
  * *![][image10]* **MACRO FACTOR**: *Brent Crude prices gap up.*  
  * *![][image10]* **INDIAN SECTOR**: *Aviation, Oil Marketing Companies (OMCs), Paints.*  
  * *![][image10]* **POTENTIAL IMPACT**: *Input costs soar. Algorithmic sell pressure on IndiGo, Asian Paints, and IOCL. The agent suppresses mean-reversion buy signals on these entities.*

## **Implementation Roadmap and Final Shortlist**

### **Recommended Staged Implementation Plan**

* **Phase 1: Macro & Calendar Infrastructure (Weeks 1-4)**  
  Connect the Trading Economics WebSocket API to capture global macroeconomic releases and economic calendar events. Connect the FRED REST API to backfill historical U.S. economic data for regime modeling. Establish the core time-series Event Store and the JSON normalization layer.  
* **Phase 2: Official Indian Regulatory Pipes (Weeks 5-8)**  
  Develop polite, rate-limited polling scripts and RSS parsers for PIB, SEBI, and RBI CIMS. Implement the LLM semantic extraction pipeline to translate these disparate PDFs and HTML releases into the Normalized Event Schema.  
* **Phase 3: Real-Time Corporate Actions (Weeks 9-12)**  
  Integrate the NSE EOD Corporate Announcements SFTP feed. While not real-time, this provides the definitive ground truth for overnight regime feature calculation, allowing the agent to anticipate morning volatility.  
* **Phase 4: Feature Generation & Integration (Weeks 13+)**  
  Deploy the Deduplication Engine and build the Feature Generation layer (Event Surprise, News Intensity, Cross-Source Velocity). Conduct extensive out-of-sample backtesting against the existing price-action execution model to calibrate the influence of the new intelligence vectors.

### **The Implementation Shortlist**

This represents the absolute minimum high-value set of sources required to materially improve the trading agent without creating an unmaintainable architectural sprawl.

| Priority | Source | Why It Matters | Data Access | Cost | Latency | Historical | Initial Integration |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **1** | Trading Economics | Replaces 50+ manual macro scrapers. Clean, timestamped calendar. | WebSocket / REST | $299/mo | Seconds | High | Phase 1 |
| **2** | FRED API | Ground truth for U.S. yields and macro. ALFRED prevents look-ahead bias. | REST API | Free | Minutes | Decades | Phase 1 |
| **3** | SEBI / RBI / PIB | Primary drivers of domestic liquidity, margin rules, and fiscal policy. | Scraper / RSS | Free | Minutes | High | Phase 2 |
| **4** | NSE EOD CA | Definitive source for Indian corporate actions without scraping risk. | SFTP | ₹5L/yr | EOD | High | Phase 3 |
| **5** | ECB / BOJ API | Vital for tracking FX carry trades and European demand metrics. | REST API | Free | EOD | High | Phase 3 |

### **Final Engineering Recommendation**

*If building a production-grade Indian intraday market-intelligence layer today from Nanakramguda, what are the minimum authoritative data sources to connect first, what should deliberately be avoided, and why?*

**What to Connect First:**

The absolute priority is the **Trading Economics WebSocket API** paired with the **FRED REST API**, supported by local **RSS/polling parsers for SEBI, RBI, and PIB**.

From a latency perspective, Nanakramguda's proximity to AWS ap-south-1 infrastructure guarantees sub-10 millisecond local processing times. However, speed is entirely negated if the system must constantly manage broken web scrapers for 50 different central bank websites. Trading Economics solves this by providing a unified, normalized WebSocket feed for global macro events. FRED provides the pristine historical data necessary to train the models without look-ahead bias. The local Indian regulatory feeds (SEBI/RBI/PIB) are mandatory because domestic structural changes instantly override global macroeconomic correlations.

**What to Deliberately Avoid:**

> 1. **Social Media and Generic Financial News (Twitter, Reddit, Tier 5 Aggregators):** Do not connect these to an automated intraday system. The noise-to-signal ratio is fatal. Social sentiment generates massive false positives, the latency is erratic, and automated execution based on unverified rumors violates core quantitative risk-management principles.  
> 2. **Scraping the NSE Website:** Attempting to scrape live option chains or corporate filings from nseindia.com via HTML parsing is an engineering dead-end. The NSE deploys aggressive anti-bot protections. It will result in IP bans and stale data, destroying the deterministic latency required for intraday execution. If real-time order book data is required, the official MTBT feed is the only viable path.  
> 3. **Expensive Institutional Feeds (Bloomberg B-PIPE, Reuters Elektron):** While they represent the industry zenith for latency and NLP capabilities, their enterprise pricing ($3,000+ monthly) and severe legal restrictions regarding algorithmic redistribution make them excessively complex and cost-prohibitive for an early-stage trading agent.

By restricting the pipeline exclusively to Tier 1 official sources and a single, highly structured Tier 2 aggregator, the architecture remains deterministic, mathematically rigorous, and auditable. It guarantees that the AI trading agent operates entirely on timestamped, verified facts, effectively isolating algorithmic execution from the hallucinations and noise of the broader internet.

*This is for informational purposes only. For medical advice or diagnosis, consult a professional.*

#### **Works cited**

> 1. AWS Network Latency Comparison. Overview | by Cloud Journey, [https://cloudjourney.medium.com/aws-network-latency-comparison-a59fea637524](https://cloudjourney.medium.com/aws-network-latency-comparison-a59fea637524)  
> 2. Corporate Filings Announcement \- Equity, SME, Debt, MF \- NSE India, [https://www.nseindia.com/companies-listing/corporate-filings-announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements)  
> 3. MARKET FEED Futures and Options (FO) \- NSE, [https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Real%20time-FO-L1L2-V1.7.pdf](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Real%20time-FO-L1L2-V1.7.pdf)  
> 4. Paid Real time data \- NSE India, [https://www.nseindia.com/static/market-data/real-time-data-subscription](https://www.nseindia.com/static/market-data/real-time-data-subscription)  
> 5. Paid Corporate Data \- NSE India, [https://www.nseindia.com/static/market-data/corporate-data-subscription](https://www.nseindia.com/static/market-data/corporate-data-subscription)  
> 6. RBI DBIE, [https://data.rbi.org.in/](https://data.rbi.org.in/)  
> 7. RBI, India CIMS Reporting \- IRIS RegTech Solutions Limited, [https://irisregtech.com/iris-ideal/en-in/rbi-cims-solution/](https://irisregtech.com/iris-ideal/en-in/rbi-cims-solution/)  
> 8. Circulars \- SEBI, [https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes\&sid=1\&ssid=7\&smid=0](https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0)  
> 9. Home Page:Press Information Bureau, [https://www.pib.gov.in/indexd.aspx?reg=3\&lang=1](https://www.pib.gov.in/indexd.aspx?reg=3&lang=1)  
> 10. Government of India \- Press Release: Press Information Bureau, [https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2299409®=3\&lang=1](https://www.pib.gov.in/PressReleaseDetail.aspx?PRID=2299409&reg=3&lang=1)  
> 11. Press Releases \- International Financial Services Centres Authority, [https://ifsca.gov.in/PressRelease/Index/MEdJSLhva0M=](https://ifsca.gov.in/PressRelease/Index/MEdJSLhva0M=)  
> 12. PFRDA notifies regulations for operationalisation of Unified Pension, [https://newsonair.gov.in/pfrda-notifies-regulations-for-operationalisation-of-unified-pension-scheme/](https://newsonair.gov.in/pfrda-notifies-regulations-for-operationalisation-of-unified-pension-scheme/)  
> 13. IRDAI Regulations & Master Circulars \[2024 \- 2025\] \- CAalley.com, [https://caalley.com/reference-section/acts-regulations-faqs/irdai-regulations-master-circulars-2024-2025](https://caalley.com/reference-section/acts-regulations-faqs/irdai-regulations-master-circulars-2024-2025)  
> 14. Trading Protocols \- NSE India, [https://www.nseindia.com/static/trade/platform-services-neat-trading-system-protocols](https://www.nseindia.com/static/trade/platform-services-neat-trading-system-protocols)  
> 15. SEBI CSCRF | CyberSigma, [https://cybersigmacs.com/knowledge-center/sebi-cscrf/](https://cybersigmacs.com/knowledge-center/sebi-cscrf/)  
> 16. Frequently Asked Questions (FAQs) on Cybersecurity and ... \- SEBI, [https://www.sebi.gov.in/sebi\_data/faqfiles/jun-2025/1749647139924.pdf](https://www.sebi.gov.in/sebi_data/faqfiles/jun-2025/1749647139924.pdf)  
> 17. SEBI Regulations on Algorithmic Trading \- StockGro, [https://www.stockgro.club/blogs/trading/sebi-regulations-on-algorithmic-trading/](https://www.stockgro.club/blogs/trading/sebi-regulations-on-algorithmic-trading/)  
> 18. Digital Loans & RBI Rules India 2026: Mobile Lending App Guide, [https://www.stashfin.com/blogs/digital-loans-mobile-lending-apps-india-guide](https://www.stashfin.com/blogs/digital-loans-mobile-lending-apps-india-guide)  
> 19. How Can Banks Automate RBI Compliance and Regulatory ... \- Nelito, [https://www.nelito.com/blog/how-can-banks-automate-rbi-compliance-and-regulatory-reporting.html](https://www.nelito.com/blog/how-can-banks-automate-rbi-compliance-and-regulatory-reporting.html)  
> 20. St. Louis Fed Web Services: FRED® API, [https://fred.stlouisfed.org/docs/api/fred/](https://fred.stlouisfed.org/docs/api/fred/)  
> 21. fred-api | Skills Marketplace \- LobeHub, [https://lobehub.com/it/skills/wentorai-research-plugins-fred-api](https://lobehub.com/it/skills/wentorai-research-plugins-fred-api)  
> 22. Getting Started : U.S. Bureau of Labor Statistics, [https://www.bls.gov/developers/home.htm](https://www.bls.gov/developers/home.htm)  
> 23. blsR: Make Requests from the Bureau of Labor Statistics API \- CRAN, [https://cran.r-project.org/web/packages/blsR/blsR.pdf](https://cran.r-project.org/web/packages/blsR/blsR.pdf)  
> 24. Free Alternatives to U.S. Bureau of Labor Statistics (BLS) (2026), [https://www.findmymoat.com/free/alternatives/u-s-bureau-of-labor-statistics-bls](https://www.findmymoat.com/free/alternatives/u-s-bureau-of-labor-statistics-bls)  
> 25. Bureau of Economic Analysis (Independent Publisher) \- Connectors, [https://learn.microsoft.com/en-us/connectors/bureauofeconomicanal/](https://learn.microsoft.com/en-us/connectors/bureauofeconomicanal/)  
> 26. SEC EDGAR MCP Server \- LobeHub, [https://lobehub.com/mcp/leopoldodonnell-edgar-mcp](https://lobehub.com/mcp/leopoldodonnell-edgar-mcp)  
> 27. FRED® API Terms of Use \- Federal Reserve Bank of St. Louis, [https://fred.stlouisfed.org/docs/api/terms\_of\_use.html](https://fred.stlouisfed.org/docs/api/terms_of_use.html)  
> 28. ecb-mcp 0.1.1 on npm \- Libraries.io \- Libraries.io, [https://libraries.io/npm/ecb-mcp](https://libraries.io/npm/ecb-mcp)  
> 29. ECB Data Portal API – Exchange Rates & Statistics \- Parse.bot, [https://parse.bot/marketplace/1bf8dbc5-e749-4b97-a1b4-b72393397bc9/data-ecb-europa-eu-api](https://parse.bot/marketplace/1bf8dbc5-e749-4b97-a1b4-b72393397bc9/data-ecb-europa-eu-api)  
> 30. BOJ Time-Series Data Search, [https://www.stat-search.boj.or.jp/index\_en.html](https://www.stat-search.boj.or.jp/index_en.html)  
> 31. boj-api 0.1.2 on PyPI \- Libraries.io, [https://libraries.io/pypi/boj-api](https://libraries.io/pypi/boj-api)  
> 32. FAQ \- Frequently Asked Questions | AllRatesToday, [https://allratestoday.com/faq/](https://allratestoday.com/faq/)  
> 33. Japan Central Bank Policy Rate Data and API | FXMacroData, [https://fxmacrodata.com/japan/policy-rate](https://fxmacrodata.com/japan/policy-rate)  
> 34. API \- Pricing \- Trading Economics, [https://tradingeconomics.com/api/pricing.aspx](https://tradingeconomics.com/api/pricing.aspx)  
> 35. API Rate Limits \- Trading Economics API Documentation, [https://docs.tradingeconomics.com/get\_started/rate-limits/](https://docs.tradingeconomics.com/get_started/rate-limits/)  
> 36. (PDF) Aggregate News Sentiment and Stock Market Returns in India, [https://www.researchgate.net/publication/373179002\_Aggregate\_News\_Sentiment\_and\_Stock\_Market\_Returns\_in\_India](https://www.researchgate.net/publication/373179002_Aggregate_News_Sentiment_and_Stock_Market_Returns_in_India)  
> 37. Aggregate News Sentiment and Stock Market Returns in India \- MDPI, [https://www.mdpi.com/1911-8074/16/8/376](https://www.mdpi.com/1911-8074/16/8/376)  
> 38. The Impact of Abnormal News Sentiment on Financial Markets, [https://www.researchgate.net/publication/280077338\_The\_Impact\_of\_Abnormal\_News\_Sentiment\_on\_Financial\_Markets](https://www.researchgate.net/publication/280077338_The_Impact_of_Abnormal_News_Sentiment_on_Financial_Markets)  
> 39. applied finance lettersVOLUME 09, 2020 \- NISM, [https://www.nism.ac.in/revamp-nism/wp-content/uploads/2021/09/15-19-PB.pdf](https://www.nism.ac.in/revamp-nism/wp-content/uploads/2021/09/15-19-PB.pdf)  
> 40. On the Relation between the Expected Value and the Volatility of the, [https://ideas.repec.org/r/bla/jfinan/v48y1993i5p1779-1801.html](https://ideas.repec.org/r/bla/jfinan/v48y1993i5p1779-1801.html)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA8AAAAaCAYAAABozQZiAAAAuklEQVR4XmNgGGjAA8SSJGAOiDYIIFsziLEZiM9D8SwgXgrEP6H4DFRsLhA/h+JysE4g0ATiHiBmhWKY2FsoDoKKgUA0FPvCBGKA2BIuDQEgBTDNIINgIBmKjWEC6gwIG2FgEhAfhmJeJHF5KOaECVCkGR0IAvFpBogBIEwSgAUWKKCQA4soAAsskCHIgUUUmMOA8Cuyf4kCZGkGBRRyYBEFDIB4IRA/gOL/QPwFiDdAsSdM4SgYBfQFAFWWKUZZIXItAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAbCAYAAABMU775AAAApklEQVR4Xu3QMQ4BQQCF4RE6EkEiUXIFlU4nep1ewzWcQ+0AOoVWtnAHjU6h0An/2Icxq5idTrJ/8lU7k9k8Y/62MtroeFooOecyNTHBAUeZYYjK59jvGkiwlOD6uGAswUVfnOKEngRll1thi6oE5Q6Tq+iL7jB+XcwlkzuM3wIDeWdHeQ2zQ837NsIGdXlmf2svN1yxNumy1hl3k774VfTFoqL8PQDVWCcCWGF0EgAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAaCAYAAABVX2cEAAAA30lEQVR4Xu3TwQoBURQG4CMpxYZEslBewVPYWNkpJc9iZWepxKPMSsnCE1jKwkJZKvH/zbk5XcNomo2av76mufd275kzXZF/SR7q0PSUoQANZeeK6i2pblaFAezhoEbQhhaM1RE2uramIlOBHUyVTUedYOjNRaYLV+grGzfGea6LDU/kya4Km7li5fyC2KS2WQ5WcNYnLdRSwkOI41z7Nbb5flzjEzXfj2t8oub7YbWs+qd+Malsxma65gcSXh8bvnPc/ZSPze/BVt3hBmt53cOJhNU84KJmUJIsWbKYPAGarjj+SKqvAgAAAABJRU5ErkJggg==>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAaCAYAAABVX2cEAAABMElEQVR4Xu3TP0vDUBQF8FtqseBfRCoVROsmWhc7lk6CdOhS3BwcHMQvoEtxcHNxcBHFxdlBJ3Eo+BX8CM4uTjq2nsM7kZe0aFICUuiBH3m5L9yX5CVmw5ZpOJBL2IYJqEmipNasAs+wKePmmr7BocRKAV5gI1LPwz1UJVbq5u6gGKlnoAXzEits1oELWBE2YvjOOA7O/0yqzWagDV3PFxxZgiZ+cuZ29Fze4RO2/It+C3eR5qIT5nb2AxpejXc5pWNPTqTf6qvwCmtebQHuzDXsSWrN+EE+SNOrBzt3bG53OV4WLsy/pPxztcKVH+UJTmEXruXW3GfBTMoZ7GkcCn/qWeHqi7Bj7lHIz5hcWfixB0qwAN8Xj+vh6WRJtVlJbmAflsLTg4V/STZaHOWf8w3BdS+dSAj12AAAAABJRU5ErkJggg==>

[image6]: <data:image/png;base64,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>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAbCAYAAABxwd+fAAAA+ElEQVR4Xu3TwQoBQRzH8b9QJFGSCzmLXJSTwybJwYkDJ8VbONlncHNSLh5AnsDF1ckLiDyCm9/f/Ldmt5Sdphz41ueyMzu7xizRz1SGLqSCA2HLwAZ2kBTGteACNWEcv9URXGGctYU4l9RijBc2rgF3wXtmXB8eYhkYC5WVhQawgrk4Q8E3gygN0cA1X0PYk9rgirhCT5vDp34NRe3aqwiMxInUZ8LFxJbUjXkxhQO0Sd3LXjlwE03votaY1EmvigksIKtP4hyytFCc1O9+98Xzq+cgIVzo6BPC5j2M96tE6tAaxf8k46Mxg7p/+POsLeTlHYt/3+oJKjYp6EtMB3QAAAAASUVORK5CYII=>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAbCAYAAACeA7ShAAABJklEQVR4Xu3Uv0pCYRgG8DeiQKoloWgKhAJraHBwcYxoCWrSrSGI8gL0ChqioZBuoEG8gS6gLqLRoSEcHISgqcXn4X0OHI+fqYcDDfXAD/V74T3fH79j9meyBJuyJRuwKMwC5GN1WlVtJOtwKQN4gzPICcPPOvSlBUXVxsKn0Au0zWeSzCnUZKY8mTdMLoHLftB4sjYxmTa7ga75YUThkhtQjo3NlCb0oBAbK5k3C+3jjzmBL/MG0Wnemi9z7mTarALf5k2rwu+pcgCfcGc+I+INSRVek3f4gH0JZQWOzB/Ogwkezhq8wlWyoGzLI+zAM+zKWDJtxunuWXifWLuXY/3mclOF16gj0Z+ar6iJezYt13IBh3Buo6+quZJpsyjLFt7X//xmhlLQK70VM7UyAAAAAElFTkSuQmCC>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAbCAYAAAB1NA+iAAAAjElEQVR4XmNgGAV0B5JA7IkuSAogywCQpm4obgZiPlRp7EAYimEaYXyCAKQIZEsHFBOlCRmQZQALENdC8WQGiJ9JBopQPBOIc4CYG4qJBhQbgAzUgXg+FIMM40SVJg3ADEuAYrIN04LiRUAchCZHFKDYAGTAgS5AMQAlpDwonkUEjoBoQwCKDRgFFAIA2vgfAk+dFWgAAAAASUVORK5CYII=>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAaCAYAAABYQRdDAAAAb0lEQVR4XmNgGAWjYHgCXSDWRBekFCgCcRq6IKWAEYjLgVgFiqkCaGIoCPAD8UQo1kOTAwMFBoSCWSTgC1C8BohFGagAXIC4AIpBwUEVQHVDQeEJiihWKKYKsAHiYHRBSgEbAxVdCAM0MXQUDBcAAKU3EX0wu3EfAAAAAElFTkSuQmCC>