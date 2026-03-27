from django.core.management.base import BaseCommand

from accounts.models import Area, City


DEFAULT_AREA_MAP = {
    "Ahmedabad": [
        "Navrangpura",
        "Maninagar",
        "Satellite",
        "Bopal",
        "Vastrapur",
    ],
    "Surat": [
        "Adajan",
        "Vesu",
        "Katargam",
        "Athwa",
        "Varachha",
    ],
    "Vadodara": [
        "Alkapuri",
        "Gotri",
        "Manjalpur",
        "Karelibaug",
        "Akota",
    ],
    "Rajkot": [
        "Kalawad Road",
        "Raiya",
        "University Road",
        "Mavdi",
        "Yagnik Road",
    ],
}


def fallback_areas(city_name):
    safe_name = city_name.replace(",", "").strip() or "City"
    return [
        f"{safe_name} Central",
        f"{safe_name} East",
        f"{safe_name} West",
    ]


class Command(BaseCommand):
    help = "Seed default areas for active cities that do not yet have any areas."

    def handle(self, *args, **kwargs):
        created_count = 0

        for city in City.objects.filter(is_active=True).order_by("name"):
            if city.areas.exists():
                continue

            area_names = DEFAULT_AREA_MAP.get(city.name, fallback_areas(city.name))
            for area_name in area_names:
                _, created = Area.objects.get_or_create(
                    city=city,
                    name=area_name,
                    defaults={"is_active": True},
                )
                if created:
                    created_count += 1

            self.stdout.write(f"Seeded {len(area_names)} areas for {city.name}")

        self.stdout.write(
            self.style.SUCCESS(f"Finished seeding areas. Created {created_count} new areas.")
        )
