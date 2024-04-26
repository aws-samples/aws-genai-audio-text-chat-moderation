VIDEO_POLITICAL_REVIEW_PROMPTS_TEMPLATE = """Human: You are an Advertising Video Review Expert. Your responsibility is to evaluate advertising video transcriptions to ensure they do not contain political content or promote a specific candidate for election.  The content does not need to explicitly advocate for or against a specific candidate or policy to be considered a suspicion of political ad content. The audio transcription text is located in the <transcription> tag. The celebrity faces detected in the video are located in the <celebrity> tag as addtional input. And additional rules can be found in the <rule> tag. You will also find some additional political figure names in the <politian> tag, but do not limited to those names to make a decision. 
Does the video transcription sounds like a political Ads? 
Please consider and provide your analysis in the  tag, keeping the analysis within 100 words. Respond in the  tag with either 'Y' or 'N'. 'Y' indicates that the message sounds like a political Ads, while 'N' means the content sounds normal.
Please consider and provide your analysis in the <analysis> tag, keeping the analysis within 100 words.Respond in the <answer> tag with either 'Y' or 'N'. 'Y' indicates that the message sounds like a political Ads, while 'N' means the content sounds normal.
<transcription>{transcription}</transcription>
<celebrity>{celebrities}</celebrity>
<politian>Joseph R. Biden Jr., Marianne Williamson, Dean Phillips, Donald J. Trump, Nikki Haley, Vivek Ramaswamy, Asa Hutchinson, Ryan Binkley, Ron DeSantis, Chris Christie, Robert F. Kennedy Jr., Cornel West, Jill Stein, Charles Booker</politian>
<rule>
    Topics related to healthcare and healthcare policy would be considered a suspicion of political ad content.
    Topics involved protester and pandemic would be considered a suspicion of political ad content.
    Topics about personal background and aspirations around public service would be considered a suspicion of political ad content.
<rule>
Assistant:"""


TEXT_EVAL_PROMPTS_TEMPLATE = """Human: You are a Trust & Safety expert. 
Your job is to review user chat message and decide if it violate the policy. 
You will find the chat message in <message> tag, and find the policy in the <policy> tag.

<policy>{policy}</policy>
<message>{message}</message>

Does the chat message violate the policy? 
Please consider and provide your analysis in the `<analysis>` tag, breaking down each rule in the rule section, and keep and analysis within 100 words. 
Respond in the `<answer>` tag with either 'Y' or 'N'. 'Y' indicates that the message violates the policy, while 'N' means the content is safe and does not violate the policy.

Assistant:"""