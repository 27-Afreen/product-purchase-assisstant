import pandas as pd
from pathlib import Path

def main():
    raw_dir = Path("data/raw")
    external_dir = Path("data/external")

    raw_dir.mkdir(parents=True, exist_ok=True)
    external_dir.mkdir(parents=True, exist_ok=True)

    products = [
        {
            "product_id": "YS001",
            "platform": "YesStyle",
            "category": "Skincare",
            "subcategory": "Cleanser",
            "brand": "COSRX",
            "product_name": "Low pH Good Morning Gel Cleanser",
            "price_original": 12.00,
            "price_discounted": 9.99,
            "currency": "USD",
            "rating_avg": 4.6,
            "review_count": 321,
            "product_url": "https://example.com/product1",
            "image_url": "https://example.com/image1.jpg",
            "size": "150ml",
            "ingredients": "Tea tree oil; BHA",
            "description": "Gentle daily cleanser for oily and combination skin.",
            "skin_type": "Oily;Combination",
            "target_concerns": "Acne;Oil control",
            "last_updated": "2026-03-24"
        },
        {
            "product_id": "YS002",
            "platform": "YesStyle",
            "category": "Skincare",
            "subcategory": "Serum",
            "brand": "Beauty of Joseon",
            "product_name": "Glow Serum",
            "price_original": 18.00,
            "price_discounted": 15.50,
            "currency": "USD",
            "rating_avg": 4.7,
            "review_count": 410,
            "product_url": "https://example.com/product2",
            "image_url": "https://example.com/image2.jpg",
            "size": "30ml",
            "ingredients": "Propolis; Niacinamide",
            "description": "Glow boosting serum for dull and uneven skin tone.",
            "skin_type": "All skin types",
            "target_concerns": "Dullness;Pigmentation",
            "last_updated": "2026-03-24"
        },
        {
            "product_id": "YS003",
            "platform": "YesStyle",
            "category": "Skincare",
            "subcategory": "Moisturizer",
            "brand": "Etude",
            "product_name": "SoonJung 2x Barrier Intensive Cream",
            "price_original": 20.00,
            "price_discounted": 17.99,
            "currency": "USD",
            "rating_avg": 4.8,
            "review_count": 280,
            "product_url": "https://example.com/product3",
            "image_url": "https://example.com/image3.jpg",
            "size": "60ml",
            "ingredients": "Panthenol; Madecassoside",
            "description": "Barrier strengthening moisturizer for sensitive skin.",
            "skin_type": "Sensitive;Dry",
            "target_concerns": "Redness;Barrier repair",
            "last_updated": "2026-03-24"
        }
    ]

    reviews = [
        {
            "review_id": "R001",
            "product_id": "YS001",
            "platform": "YesStyle",
            "review_title": "Very gentle",
            "review_text": "This cleanser feels soft and does not dry my skin.",
            "rating": 5,
            "review_date": "2026-03-20",
            "reviewer_name": "Alice",
            "skin_type": "Combination",
            "age_group": "18-24",
            "verified_purchase": True,
            "helpful_votes": 3
        },
        {
            "review_id": "R002",
            "product_id": "YS002",
            "platform": "YesStyle",
            "review_title": "Nice glow",
            "review_text": "It helped with brightness but takes time to show results.",
            "rating": 4,
            "review_date": "2026-03-19",
            "reviewer_name": "Sara",
            "skin_type": "Dry",
            "age_group": "25-34",
            "verified_purchase": True,
            "helpful_votes": 1
        },
        {
            "review_id": "R003",
            "product_id": "YS003",
            "platform": "YesStyle",
            "review_title": "Perfect for irritation",
            "review_text": "Very calming and hydrating. Good for sensitive skin.",
            "rating": 5,
            "review_date": "2026-03-18",
            "reviewer_name": "Mina",
            "skin_type": "Sensitive",
            "age_group": "25-34",
            "verified_purchase": True,
            "helpful_votes": 4
        }
    ]

    brands = [
        {
            "brand_name": "COSRX",
            "platform": "YesStyle",
            "main_category": "Skincare",
            "notes": "Popular Korean skincare brand"
        },
        {
            "brand_name": "Beauty of Joseon",
            "platform": "YesStyle",
            "main_category": "Skincare",
            "notes": "Known for glow and brightening products"
        },
        {
            "brand_name": "Etude",
            "platform": "YesStyle",
            "main_category": "Skincare",
            "notes": "Sensitive skin friendly lines"
        }
    ]

    aspect_keywords = [
        {
            "aspect": "hydration",
            "keywords": "hydrate,hydrating,moisture,moisturizing,plump,soft"
        },
        {
            "aspect": "acne",
            "keywords": "acne,pimple,breakout,blemish,spots"
        },
        {
            "aspect": "pigmentation",
            "keywords": "pigmentation,dark spots,brightening,uneven tone"
        },
        {
            "aspect": "sensitive_skin",
            "keywords": "sensitive,calming,soothing,irritation,redness"
        },
        {
            "aspect": "price",
            "keywords": "expensive,cheap,worth,pricey,affordable,budget"
        }
    ]

    pd.DataFrame(products).to_csv(raw_dir / "yesstyle_products.csv", index=False)
    pd.DataFrame(reviews).to_csv(raw_dir / "yesstyle_reviews.csv", index=False)
    pd.DataFrame(brands).to_csv(external_dir / "seed_brands.csv", index=False)
    pd.DataFrame(aspect_keywords).to_csv(external_dir / "aspect_keywords.csv", index=False)

    print("Seed datasets created successfully.")

if __name__ == "__main__":
    main()