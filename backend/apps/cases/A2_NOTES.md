# A2 intake

The agreed local fact keys are `company_name`, `company_inn`, `amount`,
`payment_date`, `payment_method`, `promised`, `happened`, and `actions_taken`.
The mock uses three synthetic scenario fixtures. Each proposed quote and value
must occur verbatim in a source from the same case. B2 independently checks the
quote again at persistence time. Images are not sent to the provider or used as
quote sources: the caller is asked to transcribe them.

Recognised immediate danger or model-classified urgency moves the case to
`emergency`: further messages, uploads, and card writes are rejected, while the
owner can read or close the case. The keyword detector is a conservative
additional check, not an exhaustive classifier. A1 provides a versioned trusted
task prompt separately from the user data. Live A2 calls are blocked before
transmission: the rules for sending real case data to an external LLM have not
been agreed (Q-S1-05). The provider and model remain unconfirmed; no five-story
live model check has been performed.
