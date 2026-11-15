import unittest
from optimization.document_qa import solve_doc_qa

CORPUS = """
THE STEAM ENGINE AND THE INDUSTRIAL REVOLUTION
Thomas Newcomen built the first practical atmospheric steam engine in 1712 for pumping water out of deep coal mines in England.
In 1769, Scottish inventor James Watt patented a separate condenser, which drastically reduced fuel consumption by 75 percent.
Watt formed a partnership with entrepreneur Matthew Boulton in 1775 in Birmingham.
The first commercial steam locomotive, named the Salamanca, was built in 1812 by Matthew Murray for the Middleton Railway in Leeds.
George Stephenson subsequently opened the Stockton and Darlington Railway in September 1825, using his locomotive named Locomotion No. 1.
The Rocket, designed by Robert Stephenson, achieved a record speed of 29 miles per hour at the Rainhill Trials in October 1829.
"""


class TestDocumentQA(unittest.TestCase):
    def test_year_question(self):
        obs = f"""DOCUMENT QA (History & Inventions). You are Player 0.
Round 1 of 5. Current score: you 0, opponent 0.

REFERENCE DOCUMENT:
{CORPUS}

QUESTION FOR ROUND 1:
  In what year did Thomas Newcomen build his atmospheric steam engine?

Instructions: Answer based strictly on the text above. If the fact is not in the text, reply 'unknown'.
"""
        ans = solve_doc_qa(obs)
        self.assertEqual(ans, "answer 1712")

    def test_person_question(self):
        obs = f"""DOCUMENT QA (History & Inventions). You are Player 0.
Round 2 of 5. Current score: you 2, opponent 0.

REFERENCE DOCUMENT:
{CORPUS}

QUESTION FOR ROUND 2:
  Who patented the separate condenser in 1769?

Instructions: Answer based strictly on the text above. If the fact is not in the text, reply 'unknown'.
"""
        ans = solve_doc_qa(obs)
        self.assertIn("Watt", ans)

    def test_name_question(self):
        obs = f"""DOCUMENT QA (History & Inventions). You are Player 0.
Round 3 of 5. Current score: you 4, opponent 0.

REFERENCE DOCUMENT:
{CORPUS}

QUESTION FOR ROUND 3:
  What was the name of the first commercial steam locomotive built in 1812?

Instructions: Answer based strictly on the text above. If the fact is not in the text, reply 'unknown'.
"""
        ans = solve_doc_qa(obs)
        self.assertIn("Salamanca", ans)

    def test_absent_question_abstention(self):
        obs = f"""DOCUMENT QA (History & Inventions). You are Player 0.
Round 4 of 5. Current score: you 6, opponent 0.

REFERENCE DOCUMENT:
{CORPUS}

QUESTION FOR ROUND 4:
  What was the diameter of the piston in Newcomen's engine?

Instructions: Answer based strictly on the text above. If the fact is not in the text, reply 'unknown'.
"""
        ans = solve_doc_qa(obs)
        self.assertEqual(ans, "unknown")


if __name__ == "__main__":
    unittest.main()
