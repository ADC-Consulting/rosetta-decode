/* 03_enrich_positions.sas
   Enrich position records with instrument and counterparty attributes.
   Compute DV01 and EUR-equivalent market value.
   A. Mehta / Quant Analytics  2020-03-15
   Updated 2022-11 to add watchlist_flg join.
*/

%m_log_step(STEP_NAME=03_enrich_positions);

/* v1 join — replaced 2022-03, kept for audit trail
PROC SQL;
  CREATE TABLE work.pos_enriched_v1 AS
  SELECT
    p.*,
    i.asset_cls_cd,
    i.ext_rating_cd,
    i.duration
  FROM work.positions p
  LEFT JOIN work.instrument_ref i
    ON p.instmt_id = i.instmt_id
  ;
QUIT;
*/

/* Current join: positions + instrument ref + counterparty */
PROC SQL;
  CREATE TABLE work.pos_enriched AS
  SELECT
    /* Position fields */
    p.trade_id,
    p.pos_dt,
    p.book_cd,
    p.desk_cd,
    p.instmt_id,
    p.qty_nom,
    p.dirty_px,
    p.mkt_val_lcy,
    p.ccy_cd,

    /* Instrument attributes */
    i.isin,
    i.issuer_id,
    i.asset_cls_cd,
    i.maturity_dt,
    i.cpn_rt,
    i.ext_rating_cd,
    i.duration,

    /* Counterparty attributes */
    c.cpty_nm,
    c.country_cd,
    c.sector_cd,
    c.int_rating_cd,
    c.watchlist_flg,

    /* DV01: standard fixed-income sensitivity formula */
    (p.qty_nom * i.duration * p.dirty_px / 10000) AS dv01,

    /* EUR-equivalent market value — hardcoded FX rates (legacy, updated quarterly by hand) */
    CASE p.ccy_cd
      WHEN 'EUR' THEN p.mkt_val_lcy * 1.00
      WHEN 'USD' THEN p.mkt_val_lcy * 0.92
      WHEN 'GBP' THEN p.mkt_val_lcy * 1.17
      ELSE             p.mkt_val_lcy * 1.00   /* default to par if ccy unknown */
    END AS mkt_val_eur,

    /* Rating band — applied from format */
    PUT(i.ext_rating_cd, $RATINGBAND.) AS rating_band

  FROM work.positions p
  LEFT JOIN work.instrument_ref i
    ON p.instmt_id = i.instmt_id
  LEFT JOIN work.counterparty c
    ON i.issuer_id = c.issuer_id

  /* Exclude positions with no market value at all (data quality filter) */
  WHERE p.mkt_val_lcy IS NOT MISSING
    AND p.mkt_val_lcy NE .
  ;
QUIT;

%m_check_obs(DSN=work.pos_enriched, CONTEXT=03_enrich_positions after join);

%PUT NOTE: [03_enrich_positions] Enriched position count: %SYSFUNC(attrn(%SYSFUNC(open(work.pos_enriched)),NOBS)).;
