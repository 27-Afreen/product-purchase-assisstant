import { useState } from "react";
import axios from "axios";
import "./App.css";

function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (!query.trim()) {
      setError("Please enter a product query.");
      setResult(null);
      return;
    }

    try {
      setLoading(true);
      setError("");
      setResult(null);

      const response = await axios.post("http://127.0.0.1:8000/recommend", {
        query: query,
      });

      setResult(response.data);
    } catch (err) {
      setError("Could not connect to backend API. Make sure FastAPI is running.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="container">
        <h1>Product Purchase Assistant</h1>
        <p className="subtitle">
          Quality-aware recommendations across skincare and home appliances
        </p>

        <div className="search-box">
          <input
            type="text"
            placeholder="Try: best smart tv under 1000 or best serum for pigmentation under 20 on yesstyle"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button onClick={handleSearch} disabled={loading}>
            {loading ? "Searching..." : "Get Recommendation"}
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        {result?.message && (
          <div className="info-box">
            <strong>Message:</strong> {result.message}
          </div>
        )}

        {result?.detected_preferences && (
          <div className="card">
            <h2>Detected Preferences</h2>
            <p><strong>Domain:</strong> {result.detected_preferences.domain || "Not detected"}</p>
            <p><strong>Category:</strong> {result.detected_preferences.category || "Not detected"}</p>
            <p>
              <strong>Platforms:</strong>{" "}
              {result.detected_preferences.platforms?.length
                ? result.detected_preferences.platforms.join(", ")
                : "Not detected"}
            </p>
            <p>
              <strong>Skin Types:</strong>{" "}
              {result.detected_preferences.skin_types?.length
                ? result.detected_preferences.skin_types.join(", ")
                : "Not detected"}
            </p>
            <p>
              <strong>Needs:</strong>{" "}
              {result.detected_preferences.needs?.length
                ? result.detected_preferences.needs.join(", ")
                : "Not detected"}
            </p>
            <p>
              <strong>Budget:</strong>{" "}
              {result.detected_preferences.budget_high !== null &&
              result.detected_preferences.budget_high !== undefined
                ? `Under $${result.detected_preferences.budget_high}`
                : "Not detected"}
            </p>
          </div>
        )}

        {result?.best_for_need && (
          <div className="card">
            <h2>Best Product For Your Need</h2>
            <p><strong>Product:</strong> {result.best_for_need.product_name}</p>
            <p><strong>Brand:</strong> {result.best_for_need.brand}</p>
            <p><strong>Platform:</strong> {result.best_for_need.platform}</p>
            <p><strong>Domain:</strong> {result.best_for_need.domain}</p>
            <p><strong>Category:</strong> {result.best_for_need.category}</p>
            <p><strong>Price:</strong> ${result.best_for_need.price}</p>
            <p><strong>Rating:</strong> {result.best_for_need.rating}</p>
            <p><strong>Review Count:</strong> {result.best_for_need.review_count}</p>
            <p><strong>Sentiment Score:</strong> {result.best_for_need.sentiment_score}</p>
            <p><strong>Quality Score:</strong> {result.best_for_need.quality_score}</p>
            <p><strong>Match Score:</strong> {result.best_for_need.match_score}</p>
            <p><strong>Use Cases:</strong> {result.best_for_need.use_cases}</p>
          </div>
        )}

        {result?.best_overall && (
          <div className="card">
            <h2>Best Overall Product</h2>
            <p><strong>Product:</strong> {result.best_overall.product_name}</p>
            <p><strong>Brand:</strong> {result.best_overall.brand}</p>
            <p><strong>Platform:</strong> {result.best_overall.platform}</p>
            <p><strong>Domain:</strong> {result.best_overall.domain}</p>
            <p><strong>Category:</strong> {result.best_overall.category}</p>
            <p><strong>Price:</strong> ${result.best_overall.price}</p>
            <p><strong>Rating:</strong> {result.best_overall.rating}</p>
            <p><strong>Review Count:</strong> {result.best_overall.review_count}</p>
            <p><strong>Sentiment Score:</strong> {result.best_overall.sentiment_score}</p>
            <p><strong>Quality Score:</strong> {result.best_overall.quality_score}</p>
            <p><strong>Overall Score:</strong> {result.best_overall.overall_score}</p>
            <p><strong>Use Cases:</strong> {result.best_overall.use_cases}</p>
          </div>
        )}

        {result?.top_matches?.length > 0 && (
          <div className="card">
            <h2>Top Matches</h2>
            <div className="matches">
              {result.top_matches.map((item, index) => (
                <div key={index} className="match-item">
                  <h3>{item.product_name}</h3>
                  <p><strong>Brand:</strong> {item.brand}</p>
                  <p><strong>Platform:</strong> {item.platform}</p>
                  <p><strong>Domain:</strong> {item.domain}</p>
                  <p><strong>Category:</strong> {item.subcategory}</p>
                  <p><strong>Price:</strong> ${item.price_discounted}</p>
                  <p><strong>Rating:</strong> {item.rating_avg}</p>
                  <p><strong>Review Count:</strong> {item.review_count}</p>
                  <p><strong>Quality Score:</strong> {item.quality_score}</p>
                  <p><strong>Match Score:</strong> {item.match_score}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;