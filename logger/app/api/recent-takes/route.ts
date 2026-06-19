import { NextResponse } from "next/server";

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY!;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID!;
const AIRTABLE_TABLE_NAME = process.env.AIRTABLE_TABLE_NAME ?? "Footage";

export async function GET() {
  const params = new URLSearchParams({
    maxRecords: "15",
    "sort[0][field]": "Logged At",
    "sort[0][direction]": "desc",
  });

  const res = await fetch(
    `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(AIRTABLE_TABLE_NAME)}?${params}`,
    {
      headers: { Authorization: `Bearer ${AIRTABLE_API_KEY}` },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    const errText = await res.text();
    return NextResponse.json({ error: errText }, { status: res.status });
  }

  const data = await res.json();
  const takes = (data.records as Array<{ id: string; fields: Record<string, unknown> }>).map(
    (r) => ({ id: r.id, ...r.fields })
  );
  return NextResponse.json({ takes });
}
