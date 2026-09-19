import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card">
      <div className="empty-state">
        <h1>Not found</h1>
        <p>The page or generation you requested does not exist.</p>
        <Link className="btn" href="/">
          Back to generation
        </Link>
      </div>
    </div>
  );
}
