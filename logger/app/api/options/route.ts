import { NextResponse } from "next/server";

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY!;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID!;

async function fetchAllRecords(table: string, fields: string[]) {
  const records: Array<{ id: string; fields: Record<string, unknown> }> = [];
  let offset: string | undefined;
  do {
    const params = new URLSearchParams();
    fields.forEach((f) => params.append("fields[]", f));
    params.set("pageSize", "100");
    if (offset) params.set("offset", offset);
    const res = await fetch(
      `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(table)}?${params}`,
      { headers: { Authorization: `Bearer ${AIRTABLE_API_KEY}` }, cache: "no-store" }
    );
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    records.push(...data.records);
    offset = data.offset;
  } while (offset);
  return records;
}

// "SCENE 23" -> "23", "SCENE 55b" -> "55b"
function stripScenePrefix(raw: string): string {
  return raw.replace(/^\s*scene\s*/i, "").trim();
}

function naturalCompare(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
}

export async function GET() {
  try {
    const [locationRecords, sceneRecords] = await Promise.all([
      fetchAllRecords("Physical Locations", ["Name", "Nickname"]),
      fetchAllRecords("Scenes", ["Scene Number"]),
    ]);

    const locations = locationRecords
      .map((r) => ({
        id: r.id,
        label: (r.fields["Nickname"] as string) || (r.fields["Name"] as string) || "(unnamed)",
      }))
      .sort((a, b) => naturalCompare(a.label, b.label));

    const scenes = sceneRecords
      .map((r) => ({
        id: r.id,
        label: stripScenePrefix((r.fields["Scene Number"] as string) || ""),
      }))
      .filter((s) => s.label)
      .sort((a, b) => naturalCompare(a.label, b.label));

    return NextResponse.json({ locations, scenes });
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
