import { NextRequest, NextResponse } from "next/server";

const AIRTABLE_API_KEY = process.env.AIRTABLE_API_KEY!;
const AIRTABLE_BASE_ID = process.env.AIRTABLE_BASE_ID!;
const AIRTABLE_TABLE_NAME = process.env.AIRTABLE_TABLE_NAME ?? "Footage";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { date, location, scene, shot, take, flaggedTake, status, notes, loggedBy } = body;

  if (!date || !location || !scene || !shot || !take) {
    return NextResponse.json(
      { error: "date, location, scene, shot, and take are required" },
      { status: 400 }
    );
  }

  const fields: Record<string, unknown> = {
    Name: `${location}_${scene}_${shot}_${String(take).padStart(2, "0")}`,
    Date: date,
    Location: location,
    Scene: scene,
    Shot: shot,
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
      body: JSON.stringify({ fields }),
    }
  );

  if (!res.ok) {
    const errText = await res.text();
    return NextResponse.json({ error: errText }, { status: res.status });
  }

  const record = await res.json();
  return NextResponse.json(record);
}
