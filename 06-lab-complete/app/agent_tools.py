"""
Outfit recommendation agent tools
Defines weather and outfit recommendation functions
"""

def get_weather(city: str, date: str) -> dict:
    """
    Get weather information for a city and date.
    
    Args:
        city (str): City name
        date (str): Date in YYYY-MM-DD format
    
    Returns:
        dict: Weather data containing temperature range and rain probability
    """
    return {
        "city": city,
        "date": date,
        "temperature_c": [27, 32],
        "rain_probability": 0.7
    }


def recommend_outfit(temp_high: int, rain_probability: float) -> str:
    """
    Recommend outfit based on weather conditions.
    
    Args:
        temp_high (int): Highest temperature in Celsius
        rain_probability (float): Rain probability (0.0 to 1.0)
    
    Returns:
        str: Outfit recommendation in Vietnamese
    """
    if rain_probability > 0.5:
        return "Áo mưa, giày dễ khô, mang theo ô gấp."
    
    if temp_high > 30:
        return "Áo nhẹ, thoáng, ưu tiên vải cotton."
    
    return "Trang phục thoải mái, có thể mang áo khoác nhẹ."


# Example usage
if __name__ == "__main__":
    # Get weather
    weather = get_weather("Hanoi", "2026-06-01")
    print("Weather data:", weather)
    
    # Recommend outfit
    outfit = recommend_outfit(
        temp_high=weather["temperature_c"][1],
        rain_probability=weather["rain_probability"]
    )
    print("Outfit recommendation:", outfit)
