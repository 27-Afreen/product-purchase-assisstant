import { useState } from "react";
import axios from "axios";
import "./App.css";

function App() {
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState("");
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSend = async () => {
    if (!message.trim()) return;

    setLoading(true);
    setError("");
    setReply("");
    setRecommendations([]);

    try {
      const response = await axios.post("http://127.0.0.1:8000/chat", {
        message: message,
      });

      setReply(response.data.reply);
      setRecommendations(response.data.recommendations || []);
    } catch (err) {
      console.error("Backend error:", err);
      if (err.response) {
        setError(`Backend error: ${err.response.status}`);
      } else if (err.request) {
        setError("Request sent, but no response from backend.");
      } else {
        setError("Frontend error while making request.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <h1>Product Purchase Assistant</h1>

      <div className="chat-box">
        <textarea
          placeholder="Ask for a product... example: I need a smart tv under 500 from Amazon"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows="4"
        />

        <button onClick={handleSend} disabled={loading}>
          {loading ? "Loading..." : "Send"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {reply && (
        <div className="response-box">
          <h2>Assistant Reply</h2>
          <p>{reply}</p>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="recommendations">
          <h2>Recommendations</h2>
          {recommendations.map((product) => (
            <div key={product.id} className="card">
              <h3>{product.name}</h3>
              <p><strong>Category:</strong> {product.category}</p>
              <p><strong>Brand:</strong> {product.brand}</p>
              <p><strong>Platform:</strong> {product.platform}</p>
              <p><strong>Price:</strong> ${product.price}</p>
              <p><strong>Rating:</strong> {product.rating}</p>
              {product.link && (
                <a href={product.link} target="_blank" rel="noreferrer">
                  View Product
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default App;