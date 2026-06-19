import { NextRequest, NextResponse } from "next/server";

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY!;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID!;
const AIRTABLE_TABLE_NAME = process.env.AIRTABLE_TABLE_NAME ?? "Footage";

function pad(value: string | number): string {
  const s = String(value);
  return /^\d+$/.test(s) ? s.padStart(2, "0") : s;
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const {
    date,
    locationId,
    locationLabel,
    sceneId,
    sceneLabel,
    shot,
    take,
    flaggedTake,
    status,
    notes,
    loggedBy,
  } = body;

  if (!date || !locationId || !sceneId || !shot || !take) {
    return NextResponse.json(
      { error: "date, locationId, sceneId, shot, and take are required" },
      { status: 400 }
    );
  }

  const fields: Record<string, unknown> = {
    Name: `${locationLabel}_${pad(sceneLabel)}_${pad(shot)}_${pad(take)}`,
    Date: date,
    "Physical Locations": [locationId],
    Scene: [sceneId],
    Shot: String(shot),
    Take: Number(take),
  };
  if (flaggedTake) fields["Flagged Take"] = true;
  if (status) fields["Status"] = status;
  if (notes) fields["Notes"] = notes;
  if (loggedBy) fields["Logged By"] = loggedBy;

  const res = await fetch(
    `https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(AIRTABLE_TABLE_NAME)}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${AIRTABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      // typecast lets a Shot number not yet in the single-select's choice list
      // still get written (Airtable adds it as a new choice) instead of erroring.
      body: JSON.stringify({ fields, typecast: true }),
    }
  );

  if (!res.ok) {
    const errText = await res.text();
    return NextResponse.json({ error: errText }, { status: res.status });
  }

  const record = await res.json();
  return NextResponse.json(record);
}
