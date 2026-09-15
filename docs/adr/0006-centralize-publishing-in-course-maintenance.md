# Centralize publishing in course maintenance

Reusable publishing, validation, renderer setup, and deployment support live in `course_maintenance`, while each course repository owns only its content, publishing configuration, and the smallest practical integration surface. This keeps behavior consistent across independently deployed course sites and avoids maintaining a separate Starlight implementation in every course repository.
