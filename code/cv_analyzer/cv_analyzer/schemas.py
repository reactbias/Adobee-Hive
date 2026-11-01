"""
Schema used with OpenAI Structured Outputs.

Rules for strict structured outputs:
  * every field must be required (no default values) -> use Optional[...] for "may be null"
  * no free-form dicts -> flexible data is modelled as a list of key/value objects
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

DegreeLevel = Literal[
    "High School", "Vocational", "Associate", "Bachelor", "Master", "MBA",
    "PhD", "Postdoc", "Certificate/Diploma", "Other",
]
CareerLevel = Literal[
    "Student/Intern", "Entry", "Mid", "Senior", "Lead/Principal",
    "Manager", "Director", "Executive",
]


class ContactInfo(BaseModel):
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str] = Field(description="Current city/region as written on the CV")
    country: Optional[str] = Field(description="Country of current residence, if stated or clear")
    website: Optional[str] = Field(description="Personal website/portfolio URL")


class SocialLink(BaseModel):
    platform: Literal["LinkedIn", "GitHub", "GitLab", "Medium", "Kaggle", "StackOverflow",
                      "Twitter/X", "Portfolio", "Google Scholar", "Other"]
    url: str


class WorkExperience(BaseModel):
    job_title: Optional[str]
    job_category: Optional[str] = Field(
        description="Broad job family, e.g. 'Data Science', 'Software Engineering', 'Sales'")
    company: Optional[str]
    industry: Optional[str] = Field(description="e.g. 'Technology', 'Healthcare', 'Banking'")
    location: Optional[str]
    country: Optional[str]
    employment_type: Optional[Literal["Full-time", "Part-time", "Contract", "Freelance",
                                      "Internship", "Apprenticeship", "Other"]]
    start_date: Optional[str] = Field(description="YYYY-MM or YYYY")
    end_date: Optional[str] = Field(description="YYYY-MM, YYYY or 'Present'")
    is_current: bool
    duration_months: Optional[int] = Field(description="Only if stated or computable from dates")
    team_size_managed: Optional[int] = Field(description="Number of direct/indirect reports if stated")
    responsibilities: list[str]
    achievements: list[str] = Field(description="Measurable outcomes (numbers, %, scale)")


class Education(BaseModel):
    degree: Optional[str] = Field(description="e.g. 'BSc Computer Science'")
    degree_level: Optional[DegreeLevel]
    field_of_study: Optional[str]
    institution: Optional[str]
    country: Optional[str]
    start_date: Optional[str]
    graduation_date: Optional[str] = Field(description="YYYY-MM or YYYY; 'Expected YYYY' if ongoing")
    grade: Optional[str] = Field(description="GPA / grade / classification if stated")
    honors: list[str] = Field(description="Honors, scholarships, dean's list, awards")


class Certification(BaseModel):
    name: str
    issuer: Optional[str]
    date: Optional[str]


class Language(BaseModel):
    language: str
    proficiency: Optional[str] = Field(description="As written, e.g. 'Native', 'C1', 'Fluent'")


class Project(BaseModel):
    name: Optional[str]
    description: str
    technologies: list[str]
    outcome: Optional[str]


class Publication(BaseModel):
    title: str
    type: Literal["Publication", "Patent", "Talk/Conference", "Thesis", "Other"]
    venue: Optional[str]
    date: Optional[str]


class VolunteerWork(BaseModel):
    organization: Optional[str]
    role: Optional[str]
    description: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]


class ExtraField(BaseModel):
    """Catch-all for anything that does not fit the default fields."""
    key: str = Field(description="short snake_case key, e.g. 'work_permit', 'notice_period'")
    value: str
    section: Optional[str] = Field(description="CV section where this was found")


class CustomFieldAnswer(BaseModel):
    """Answer to a position-specific question defined by the recruiter."""
    field_name: str
    value: Optional[str]
    evidence: Optional[str] = Field(description="Short quote from the CV supporting the value")
    confidence: Literal["high", "medium", "low", "not_found"]


class QualitySignals(BaseModel):
    generic_phrases: list[str] = Field(
        description="Up to 5 vague statements without context/action/result")
    unsubstantiated_skills: list[str] = Field(
        description="Skills listed but not backed by any role, project or achievement")
    notes: Optional[str] = Field(description="Anything odd: unreadable parts, inconsistencies")


class CVExtraction(BaseModel):
    contact: ContactInfo
    social_links: list[SocialLink]
    professional_summary: Optional[str] = Field(description="1-3 sentence neutral summary")
    current_job_title: Optional[str]
    career_level: Optional[CareerLevel]
    total_years_experience: Optional[float]
    job_categories: list[str] = Field(description="Unique broad job families, most recent first")
    industry_sectors: list[str]
    work_experience: list[WorkExperience]
    education: list[Education]
    highest_education_level: Optional[DegreeLevel]
    certifications: list[Certification]
    technical_skills: list[str]
    soft_skills: list[str]
    software_and_tools: list[str]
    languages: list[Language]
    projects: list[Project]
    publications_or_patents: list[Publication]
    volunteer_work: list[VolunteerWork]
    awards: list[str]
    continuous_learning: list[str] = Field(
        description="Courses, MOOCs, bootcamps, self-study, recent upskilling")
    key_takeaways: list[str] = Field(description="Up to 5 key themes of the profile")
    quality: QualitySignals
    additional_info: list[ExtraField]
    custom_fields: list[CustomFieldAnswer]
    cv_language: Optional[str] = Field(description="Language the CV is written in")

class RelevanceScreening(BaseModel):
    """Gate decision: is this CV a plausible fit for the job posting?"""
    relevant: bool = Field(description="True if the candidate should be considered for this job")
    score: int = Field(description="Fit score 0-100 (0 = unrelated field, 100 = ideal match)")
    candidate_name: Optional[str]
    matched_requirements: list[str] = Field(description="Up to 5 job requirements the CV satisfies")
    missing_requirements: list[str] = Field(description="Up to 5 key job requirements the CV lacks")
    reason: str = Field(description="One or two sentences justifying the decision")
