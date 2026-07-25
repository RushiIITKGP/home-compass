import type { Recommendation } from "@/lib/types";

interface ListingCardProps {
  recommendation: Recommendation;
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function ListingCard({ recommendation }: ListingCardProps) {
  const { listing, fit_score, enrichment } = recommendation;
  const pct = fit_score != null ? Math.round(fit_score * 100) : null;

  const demographics = enrichment.demographics && !enrichment.demographics.error ? enrichment.demographics : null;
  const safety = enrichment.safety && !enrichment.safety.error ? enrichment.safety : null;
  const market = enrichment.market && !enrichment.market.error ? enrichment.market.redfin ?? enrichment.market.realtor_com : null;

  return (
    <article className="rounded-lg border border-rule bg-ink-2 p-4 flex flex-col gap-3">
      {/* Header: address + recommendation confidence, like a stamped record */}
      <header className="flex items-start justify-between gap-3 border-b border-rule pb-3">
        <div>
          <h3 className="font-display text-lg leading-snug text-parchment">{listing.address}</h3>
          <p className="font-mono text-xs text-muted mt-1">
            {listing.city}
            {listing.city && listing.state ? ", " : ""}
            {listing.state} {listing.zip_code}
          </p>
        </div>
        {pct != null && (
          <span
            className="shrink-0 rounded-full border border-brass/50 bg-brass/10 px-2 py-0.5 font-mono text-xs text-brass-bright tabular-nums"
            title="Fit — how well this listing matches your stated criteria (budget, location, beds, baths)"
          >
            fit {pct}%
          </span>
        )}
      </header>

      {/* Core listing facts */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-sm">
        <div className="flex justify-between col-span-2">
          <dt className="text-muted">price</dt>
          <dd className="text-parchment">{formatPrice(listing.price)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">beds</dt>
          <dd className="text-parchment">{listing.beds ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">baths</dt>
          <dd className="text-parchment">{listing.baths ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">sqft</dt>
          <dd className="text-parchment">{listing.sqft ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">status</dt>
          <dd className="text-parchment">{listing.status ?? "—"}</dd>
        </div>
      </dl>

      {/* Enrichment — each figure carries its source, like a field note */}
      {(demographics || safety || market) && (
        <div className="border-t border-rule pt-3 flex flex-col gap-2.5">
          {demographics && (
            <EnrichmentRow
              label="income"
              value={
                demographics.median_household_income != null
                  ? `${formatPrice(demographics.median_household_income)} median household`
                  : "—"
              }
              source="US Census ACS 5-Year"
            />
          )}
          {safety && (
            <EnrichmentRow
              label="safety"
              value={
                safety.violent_crime_count != null
                  ? `${safety.violent_crime_count.toLocaleString()} violent, ${(safety.property_crime_count ?? 0).toLocaleString()} property (${safety.year}, statewide est.)`
                  : "—"
              }
              source="FBI Crime Data API"
            />
          )}
          {market && (
            <EnrichmentRow
              label="market"
              value={
                market.median_sale_price != null
                  ? `${formatPrice(market.median_sale_price)} median, ${market.inventory_count ?? "—"} listed`
                  : "—"
              }
              source={market.source === "redfin" ? "Redfin Data Center" : "Realtor.com Data Library"}
            />
          )}
        </div>
      )}

      {!demographics && !safety && !market && (
        <p className="text-xs text-muted italic border-t border-rule pt-3">
          No neighborhood data available for this ZIP yet.
        </p>
      )}
    </article>
  );
}

function EnrichmentRow({ label, value, source }: { label: string; value: string; source: string }) {
  return (
    <div className="text-sm">
      <div className="flex justify-between gap-2">
        <span className="font-mono text-xs uppercase tracking-wide text-verdigris-bright shrink-0">{label}</span>
        <span className="text-parchment text-right">{value}</span>
      </div>
      <p className="font-mono text-[10px] text-muted text-right mt-0.5">source: {source}</p>
    </div>
  );
}
