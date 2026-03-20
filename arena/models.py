from django.conf import settings
from django.db import models
from django.utils import timezone


class ArenaProfile(models.Model):
    TIER_BRONZE = "Bronze"
    TIER_SILVER = "Silver"
    TIER_GOLD = "Gold"
    TIER_PLATINUM = "Platinum"
    TIER_DIAMOND = "Diamond"
    TIER_CHALLENGER = "Challenger"

    TIER_CHOICES = [
        (TIER_BRONZE, "Bronze"),
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
        (TIER_PLATINUM, "Platinum"),
        (TIER_DIAMOND, "Diamond"),
        (TIER_CHALLENGER, "Challenger"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arena_profile"
    )
    tier = models.CharField(
        max_length=20,
        choices=TIER_CHOICES,
        default=TIER_BRONZE
    )
    best_capital = models.BigIntegerField(default=0)
    bonus_turns = models.PositiveIntegerField(default=0)
    total_posts = models.PositiveIntegerField(default=0)
    total_answers = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.tier}"


class Question(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arena_questions"
    )
    voter = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="voted_arena_questions",
        blank=True
    )
    subject = models.CharField(max_length=200)
    content = models.TextField()
    create_date = models.DateTimeField(default=timezone.now)
    modify_date = models.DateTimeField(null=True, blank=True)
    views = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to="question_images/", null=True, blank=True)

    class Meta:
        ordering = ["-create_date"]

    def __str__(self):
        return self.subject

    @property
    def vote_count(self):
        return self.voter.count()

    @property
    def answer_count(self):
        return self.answers.count()

    @property
    def author_tier(self):
        if hasattr(self.author, "arena_profile") and self.author.arena_profile:
            return self.author.arena_profile.tier
        return "Bronze"


class Answer(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="arena_answers"
    )
    voter = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="voted_arena_answers",
        blank=True
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    content = models.TextField()
    create_date = models.DateTimeField(default=timezone.now)
    modify_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["create_date"]

    def __str__(self):
        return f"Answer by {self.author.username} on {self.question.subject}"

    @property
    def vote_count(self):
        return self.voter.count()

    @property
    def author_tier(self):
        if hasattr(self.author, "arena_profile") and self.author.arena_profile:
            return self.author.arena_profile.tier
        return "Bronze"