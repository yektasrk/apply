import pandas as pd

from job_finder import config
from job_finder.scraper import mark_title_mismatches


def test_mark_title_mismatches_marks_requested_keywords():
    jobs = pd.DataFrame(
        {
            "title": [
                "Senior Staff Engineer",
                "AWS Platform Engineer",
                "Data Center Operations Engineer",
                "OpenShift Administrator",
                "Windows Systems Engineer",
                "Microsoft Cloud Engineer",
                "Platform Engineer",
            ],
            "job_url": [f"https://example.com/{i}" for i in range(7)],
        }
    )

    marked = mark_title_mismatches(jobs)

    assert marked["job_status"].tolist() == [
        "Not Suitable",
        "Not Suitable",
        "Not Suitable",
        "Not Suitable",
        "Not Suitable",
        "Not Suitable",
        "",
    ]
    assert marked.loc[:5, "suitability_reason"].tolist() == [
        config.TITLE_MISMATCH_REASON
    ] * 6
    assert marked.loc[6, "suitability_reason"] == ""


def test_title_matching_is_whole_word_aware_and_case_insensitive():
    jobs = pd.DataFrame(
        {
            "title": ["Staffing Coordinator", "mlops Engineer", "Data Centre Engineer"],
        }
    )

    marked = mark_title_mismatches(jobs)

    assert marked["job_status"].tolist() == ["", "Not Suitable", ""]
